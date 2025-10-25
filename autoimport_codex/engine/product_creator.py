"""Create new Shopify products based on parsed CSV rows and AI content."""
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

import pandas as pd
import requests
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "config" / "codex.yaml"
DATA_DIR = ROOT_DIR / "data"
NEW_PRODUCTS_PATH = DATA_DIR / "new_products.json"
DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_yaml(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_new_products() -> pd.DataFrame:
    if NEW_PRODUCTS_PATH.exists():
        return pd.read_json(NEW_PRODUCTS_PATH)
    return pd.DataFrame()


def ai_generate_text(title: str, category: str) -> str:
    """Simple AI placeholder until GPT-5 integration is available."""
    intro = f"{title} er et solid valg for deg som driver med {category.lower()}." if category else f"{title} er et solid valg for friluftsliv."
    specs = "Robust konstruksjon, god ergonomi og høy slitestyrke."
    why = "Utviklet for norske forhold – perfekt for jakt, fiske og friluft."
    return f"<h2>Om produktet</h2><p>{intro}</p><h2>Egenskaper</h2><ul><li>{specs}</li></ul><p>{why}</p>"


def create_product(row: pd.Series, cfg: Dict[str, object], dry_run: bool = True) -> None:
    body_html = row.get("description_html") or ai_generate_text(row.get("title", "Produkt"), row.get("category", "Friluft"))
    payload = {
        "product": {
            "title": row.get("title"),
            "body_html": body_html,
            "vendor": row.get("vendor"),
            "product_type": row.get("category"),
            "status": row.get("status", "draft"),
            "variants": [
                {
                    "sku": row.get("sku"),
                    "price": row.get("price"),
                    "compare_at_price": row.get("compare_at_price"),
                    "inventory_quantity": int(row.get("inventory_quantity") or 0),
                }
            ],
            "images": [{"src": row.get("image_url")}]
            if pd.notna(row.get("image_url")) and row.get("image_url")
            else [],
        }
    }

    if dry_run:
        print(f"🧪 [Dry-run] Ville opprettet produkt: {row.get('title')} ({row.get('sku')})")
        return

    url = f"https://{cfg['shopify_store_url']}/admin/api/2024-10/products.json"
    headers = {
        "X-Shopify-Access-Token": cfg["shopify_token"],
        "Content-Type": "application/json",
    }
    response = requests.post(url, headers=headers, json=payload, timeout=30)
    if response.ok:
        print(f"✅ Opprettet {row.get('title')}")
    else:
        print(f"❌ Feil: {response.status_code} – {response.text[:200]}")


def main(dry_run: bool = True) -> None:
    print(f"🚀 Oppretter nye produkter – {datetime.now():%Y-%m-%d %H:%M}")
    cfg = load_yaml(CONFIG_PATH)
    df = load_new_products()
    if df.empty:
        print("Ingen nye produkter å opprette.")
        return

    for _, row in df.iterrows():
        create_product(row, cfg, dry_run=dry_run)
        time.sleep(random.uniform(0.3, 0.6))

    print("Ferdig ✅")


if __name__ == "__main__":
    main(dry_run=True)
