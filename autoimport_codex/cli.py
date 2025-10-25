"""Command line interface for running the Shopify autoimport pipeline."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from .engine.import_parser import load_import_config, parse_product_feed
from .engine.inventory_sync import (
    InventoryDiff,
    InventoryRules,
    calculate_inventory_diff,
    load_cache,
    save_cache,
)
from .engine.product_creator import DATA_DIR, NEW_PRODUCTS_PATH
from .engine.shopify_sync import build_sync_from_config

ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "config" / "codex.yaml"


def _load_inventory_rules() -> InventoryRules:
    """Extract inventory rules from the codex config if available."""

    # load_import_config only returns mapping + ai settings, so we read codex again
    config_blob = {}
    if CONFIG_PATH.exists():
        import yaml

        with CONFIG_PATH.open("r", encoding="utf-8") as handle:
            config_blob = yaml.safe_load(handle) or {}

    rule_conf = config_blob.get("inventory_rules", {})
    match_by = rule_conf.get("match_by", ("sku", "barcode"))
    return InventoryRules(
        match_by=match_by,
        set_inventory_exact=rule_conf.get("set_inventory_exact", True),
        skip_if_no_change=rule_conf.get("skip_if_no_change", True),
    )


def run_pipeline(
    csv_path: Path,
    dry_run: bool = True,
    update_cache: bool = False,
    save_new_products: bool = True,
    delimiter: str = ",",
) -> InventoryDiff:
    """Execute the import, diff, and optional Shopify sync workflow."""

    csv_path = Path(csv_path)
    import_config = load_import_config()
    rules = _load_inventory_rules()
    current_df = parse_product_feed(csv_path, delimiter=delimiter, config=import_config)
    cache_df = load_cache()

    diff = calculate_inventory_diff(current_df, cache_df, rules=rules)

    if save_new_products:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        diff.new_items.to_json(NEW_PRODUCTS_PATH, orient="records", force_ascii=False, indent=2)

    sync_client = build_sync_from_config(dry_run=dry_run)
    if not diff.changed_items.empty:
        sync_client.sync_changed_inventory(diff.changed_items)
    if not diff.new_items.empty:
        sync_client.sync_new_products(diff.new_items)

    if update_cache:
        save_cache(current_df)

    return diff


def _format_summary(diff: InventoryDiff) -> str:
    return (
        "\n".join(
            [
                f"Nye produkter: {len(diff.new_items)}",
                f"Endrede produkter: {len(diff.changed_items)}",
                f"Uendrede produkter: {len(diff.unchanged_items)}",
                f"Fjernede produkter: {len(diff.removed_items)}",
            ]
        )
        + "\n"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kjør autoimport-pipelinen mot Shopify.")
    parser.add_argument("csv", type=Path, help="Sti til Shopify CSV-eksporten")
    parser.add_argument(
        "--delimiter",
        default=",",
        help="Avgrenser brukt i CSV-filen (standard ',').",
    )
    dry_group = parser.add_mutually_exclusive_group()
    dry_group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Kjør uten å gjøre endringer i Shopify (standard).",
    )
    dry_group.add_argument(
        "--apply",
        dest="dry_run",
        action="store_false",
        help="Utfør faktiske endringer i Shopify.",
    )
    parser.set_defaults(dry_run=True)
    parser.add_argument(
        "--update-cache",
        action="store_true",
        help="Oppdater cache_inventory.csv etter vellykket kjøring.",
    )
    parser.add_argument(
        "--no-new-products-file",
        dest="save_new_products",
        action="store_false",
        help="Unngå å skrive data/new_products.json.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    diff = run_pipeline(
        csv_path=args.csv,
        dry_run=args.dry_run,
        update_cache=args.update_cache,
        save_new_products=args.save_new_products,
        delimiter=args.delimiter,
    )
    print("\n=== Sammendrag ===")
    print(_format_summary(diff))
    if args.save_new_products:
        print(f"Detaljer for nye produkter er lagret i {NEW_PRODUCTS_PATH}")


if __name__ == "__main__":
    main()
