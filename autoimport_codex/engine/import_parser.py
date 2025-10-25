"""Utilities for parsing Shopify CSV product feeds into a normalized dataframe."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd
import yaml

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "config" / "codex.yaml"
FIELD_MAPPING_PATH = ROOT_DIR / "config" / "field_mapping.yaml"
LOG_DIR = ROOT_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGER = logging.getLogger(__name__)
if not LOGGER.handlers:
    file_handler = logging.FileHandler(LOG_DIR / "import_parser.log")
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)
    LOGGER.setLevel(logging.INFO)


@dataclass
class ImportConfig:
    """Configuration values required for CSV parsing."""

    mapping: Dict[str, str]
    ai_settings: Dict[str, object]


class ImportParserError(RuntimeError):
    """Raised when the parser encounters invalid input."""


def load_yaml(path: Path) -> Dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_import_config(
    field_mapping_path: Path = FIELD_MAPPING_PATH,
    config_path: Path = CONFIG_PATH,
) -> ImportConfig:
    mapping_blob = load_yaml(field_mapping_path)
    config_blob = load_yaml(config_path)

    try:
        mapping = mapping_blob["field_mapping"]
    except KeyError as exc:
        raise ImportParserError("field_mapping.yaml mangler 'field_mapping'-nøkkel") from exc

    ai_settings = config_blob.get("ai_content", {})
    return ImportConfig(mapping=mapping, ai_settings=ai_settings)


def _rename_columns(df: pd.DataFrame, mapping: Dict[str, str]) -> pd.DataFrame:
    rename_map = {source: target for target, source in mapping.items() if source in df.columns}
    LOGGER.info("Renaming columns using mapping: %s", rename_map)
    df = df.rename(columns={source: target for target, source in mapping.items()})
    return df


def _ensure_columns(df: pd.DataFrame, expected: Iterable[str]) -> pd.DataFrame:
    missing = [column for column in expected if column not in df.columns]
    if missing:
        raise ImportParserError(f"CSV mangler kolonnene: {', '.join(missing)}")
    return df


def _clean_whitespace(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    for column in columns:
        if column in df.columns:
            df[column] = df[column].astype(str).str.strip().replace({"nan": None})
    return df


def _convert_numeric(df: pd.DataFrame, numeric_columns: Iterable[str]) -> pd.DataFrame:
    for column in numeric_columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
    return df


def parse_product_feed(
    csv_path: Path,
    delimiter: str = ",",
    config: Optional[ImportConfig] = None,
) -> pd.DataFrame:
    """Parse a Shopify CSV export into a normalized dataframe."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        raise ImportParserError(f"Fant ikke CSV-fil: {csv_path}")

    if config is None:
        config = load_import_config()

    LOGGER.info("Leser CSV: %s", csv_path)
    df = pd.read_csv(csv_path, delimiter=delimiter, keep_default_na=False)
    df = _rename_columns(df, config.mapping)
    df = _ensure_columns(df, config.mapping.keys())
    text_columns: List[str] = ["handle", "title", "vendor", "category", "description_html"]
    df = _clean_whitespace(df, text_columns)
    numeric_columns = ["inventory_quantity", "price", "compare_at_price"]
    df = _convert_numeric(df, numeric_columns)

    df = df.drop_duplicates(subset=["sku"], keep="last")
    df = df[df["status"].str.lower().isin({"active", "draft"})]
    LOGGER.info("Ferdig behandlet %s rader", len(df))
    return df.reset_index(drop=True)


__all__ = [
    "ImportConfig",
    "ImportParserError",
    "load_import_config",
    "parse_product_feed",
]
