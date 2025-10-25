"""Synchronize inventory and products with the Shopify Admin API."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import requests
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "config" / "codex.yaml"
LOG_DIR = ROOT_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGER = logging.getLogger(__name__)
if not LOGGER.handlers:
    handler = logging.FileHandler(LOG_DIR / "shopify_sync.log")
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


@dataclass
class ShopifyCredentials:
    store_url: str
    token: str
    api_version: str = "2024-10"


def load_config(path: Path = CONFIG_PATH) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


class ShopifySync:
    def __init__(self, credentials: ShopifyCredentials, dry_run: bool = True) -> None:
        self.credentials = credentials
        self.dry_run = dry_run
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Shopify-Access-Token": credentials.token,
                "Content-Type": "application/json",
            }
        )

    # URL builder
    def _endpoint(self, path: str) -> str:
        return f"https://{self.credentials.store_url}/admin/api/{self.credentials.api_version}/{path.lstrip('/')}"

    def _request(self, method: str, path: str, payload: Optional[Dict[str, object]] = None) -> Dict[str, object]:
        if self.dry_run:
            LOGGER.info("[Dry-run] %s %s payload=%s", method.upper(), path, json.dumps(payload, ensure_ascii=False))
            return {"dry_run": True, "payload": payload or {}, "endpoint": path}
        response = self.session.request(method.upper(), self._endpoint(path), json=payload, timeout=30)
        if not response.ok:
            LOGGER.error("Shopify API-feil %s: %s", response.status_code, response.text[:500])
            response.raise_for_status()
        LOGGER.info("Shopify API %s %s OK", method.upper(), path)
        if response.text:
            return response.json()
        return {}

    # Build variant payload
    def _build_variant_payload(self, row: Dict[str, object]) -> Dict[str, object]:
        variant_payload: Dict[str, object] = {
            "sku": row.get("sku"),
            "price": row.get("price"),
            "compare_at_price": row.get("compare_at_price"),
        }
        inventory_quantity = row.get("inventory_quantity")
        if inventory_quantity is not None:
            variant_payload["inventory_quantity"] = int(inventory_quantity)
        return variant_payload

    def create_product(self, row: Dict[str, object]) -> Dict[str, object]:
        payload = {
            "product": {
                "title": row.get("title"),
                "body_html": row.get("description_html"),
                "handle": row.get("handle"),
                "vendor": row.get("vendor"),
                "product_type": row.get("category"),
                "status": row.get("status", "draft"),
                "variants": [self._build_variant_payload(row)],
            }
        }
        if row.get("image_url"):
            payload["product"]["images"] = [{"src": row["image_url"]}]
        LOGGER.debug("Create payload: %s", payload)
        return self._request("post", "products.json", payload)

    def update_variant_by_sku(self, sku: str, payload: Dict[str, object]) -> Dict[str, object]:
        body = {"variant": payload}
        endpoint = f"variants.json?sku={sku}"
        return self._request("put", endpoint, body)

    def sync_changed_inventory(self, changed_items) -> None:
        if changed_items is None or changed_items.empty:
            LOGGER.info("Ingen endrede produkter å synkronisere")
            return
        for _, row in changed_items.iterrows():
            sku = row.get("sku")
            if not sku:
                LOGGER.warning("Hopper over rad uten SKU: %s", row.to_dict())
                continue
            variant_payload = self._build_variant_payload(row)
            LOGGER.info("Oppdaterer SKU %s med payload %s", sku, variant_payload)
            self.update_variant_by_sku(sku, variant_payload)

    def sync_new_products(self, new_items) -> None:
        if new_items is None or new_items.empty:
            LOGGER.info("Ingen nye produkter å opprette i Shopify")
            return
        for _, row in new_items.iterrows():
            LOGGER.info("Oppretter nytt produkt %s", row.get("title"))
            self.create_product(row.to_dict())


def build_sync_from_config(config_path: Path = CONFIG_PATH, dry_run: bool = True) -> ShopifySync:
    config = load_config(config_path)
    credentials = ShopifyCredentials(
        store_url=config.get("shopify_store_url", ""),
        token=config.get("shopify_token", ""),
    )
    return ShopifySync(credentials, dry_run=dry_run)


__all__ = ["ShopifySync", "ShopifyCredentials", "build_sync_from_config"]
