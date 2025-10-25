"""Inventory comparison helpers for the autoimport pipeline."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT_DIR / "data" / "cache_inventory.csv"
LOG_DIR = ROOT_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGER = logging.getLogger(__name__)
if not LOGGER.handlers:
    handler = logging.FileHandler(LOG_DIR / "inventory_sync.log")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


@dataclass
class InventoryRules:
    match_by: Iterable[str]
    set_inventory_exact: bool = True
    skip_if_no_change: bool = True


@dataclass
class InventoryDiff:
    new_items: pd.DataFrame
    changed_items: pd.DataFrame
    unchanged_items: pd.DataFrame
    removed_items: pd.DataFrame


def _build_match_key(df: pd.DataFrame, match_fields: Iterable[str]) -> pd.Series:
    return df[list(match_fields)].fillna("").astype(str).agg("||".join, axis=1)


def load_cache(path: Path = CACHE_PATH) -> pd.DataFrame:
    if path.exists():
        LOGGER.info("Laster cache fra %s", path)
        return pd.read_csv(path)
    LOGGER.info("Ingen cache funnet på %s", path)
    return pd.DataFrame()


def save_cache(df: pd.DataFrame, path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    LOGGER.info("Cache oppdatert: %s", path)


def calculate_inventory_diff(
    current_df: pd.DataFrame,
    cache_df: Optional[pd.DataFrame] = None,
    rules: Optional[InventoryRules] = None,
) -> InventoryDiff:
    if rules is None:
        rules = InventoryRules(match_by=("sku", "barcode"))
    if cache_df is None or cache_df.empty:
        LOGGER.info("Cache er tom – alle produkter behandles som nye")
        empty = pd.DataFrame(columns=current_df.columns)
        return InventoryDiff(new_items=current_df, changed_items=empty, unchanged_items=empty, removed_items=pd.DataFrame(columns=current_df.columns))

    required_fields = list(rules.match_by)
    missing_fields = [field for field in required_fields if field not in current_df.columns]
    if missing_fields:
        raise ValueError(f"Manglende felt i nåværende feed: {missing_fields}")

    cache_missing = [field for field in required_fields if field not in cache_df.columns]
    if cache_missing:
        raise ValueError(f"Cache mangler felt: {cache_missing}")

    current_df = current_df.copy()
    cache_df = cache_df.copy()
    current_df["_match_key"] = _build_match_key(current_df, rules.match_by)
    cache_df["_match_key"] = _build_match_key(cache_df, rules.match_by)
    cache_df = cache_df.drop_duplicates("_match_key", keep="last").set_index("_match_key")
    base_columns = [col for col in current_df.columns if col != "_match_key"]

    new_rows = []
    changed_rows = []
    unchanged_rows = []

    for _, row in current_df.iterrows():
        key = row["_match_key"]
        if key not in cache_df.index:
            new_rows.append(row)
            continue
        cache_row = cache_df.loc[key]
        changed = False
        comparisons: Dict[str, object] = {}
        for column in ["inventory_quantity", "price", "compare_at_price"]:
            current_value = row.get(column)
            previous_value = cache_row.get(column)
            if pd.isna(current_value) and pd.isna(previous_value):
                continue
            if current_value != previous_value:
                changed = True
                comparisons[column] = {"old": previous_value, "new": current_value}
        if changed:
            enriched = row.to_dict()
            enriched["_changes"] = comparisons
            changed_rows.append(enriched)
        else:
            unchanged_rows.append(row)

    removed_mask = ~cache_df.index.isin(current_df["_match_key"])
    removed_rows = cache_df[removed_mask].reset_index(drop=True)

    new_df = pd.DataFrame(new_rows)
    if not new_df.empty:
        new_df = new_df.drop(columns=["_match_key"], errors="ignore")
    else:
        new_df = pd.DataFrame(columns=base_columns)
    changed_df = pd.DataFrame(changed_rows)
    if changed_df.empty:
        changed_df = pd.DataFrame(columns=base_columns + ["_changes"])
    elif "_match_key" in changed_df.columns:
        changed_df = changed_df.drop(columns=["_match_key"], errors="ignore")
    unchanged_df = pd.DataFrame(unchanged_rows)
    if not unchanged_df.empty:
        unchanged_df = unchanged_df.drop(columns=["_match_key"], errors="ignore")
    else:
        unchanged_df = pd.DataFrame(columns=base_columns)

    LOGGER.info(
        "Inventory diff – nye: %s, endret: %s, uendret: %s, fjernet: %s",
        len(new_df),
        len(changed_df),
        len(unchanged_df),
        len(removed_rows),
    )

    return InventoryDiff(
        new_items=new_df,
        changed_items=changed_df,
        unchanged_items=unchanged_df,
        removed_items=removed_rows,
    )


__all__ = [
    "InventoryDiff",
    "InventoryRules",
    "calculate_inventory_diff",
    "load_cache",
    "save_cache",
]
