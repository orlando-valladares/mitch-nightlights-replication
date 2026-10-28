from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


MISSING_TOKENS = {"", " ", "NA", "N/A", "NULL", "NONE", "-99", "-999", "-9999"}


def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df


def to_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.replace(list(MISSING_TOKENS), np.nan), errors="coerce")


def normalize_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def first_existing_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    lookup = {str(c).lower(): c for c in df.columns}
    for candidate in candidates:
        col = lookup.get(candidate.lower())
        if col is not None:
            return col
    return None


def make_gaul_muni_key(df: pd.DataFrame) -> pd.Series | None:
    cols = [first_existing_column(df, [c]) for c in ["ADM0_CODE", "ADM1_CODE", "ADM2_CODE"]]
    if any(col is None for col in cols):
        return None
    parts = [to_numeric(df[col]).astype("Int64").astype(str) for col in cols if col is not None]
    return parts[0] + "_" + parts[1] + "_" + parts[2]


def ensure_muni_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Add common municipality fields used throughout the pipeline."""
    df = clean_column_names(df)
    if "muni_key" not in df.columns:
        gaul_key = make_gaul_muni_key(df)
        if gaul_key is not None:
            df["muni_key"] = gaul_key
        else:
            id_col = first_existing_column(
                df,
                [
                    "shapeID",
                    "shape_id",
                    "GID_2",
                    "ADM2_PCODE",
                    "ADM2_CODE",
                    "id",
                    "ID",
                ],
            )
            if id_col is not None:
                df["muni_key"] = df[id_col].astype(str)
    name_col = first_existing_column(
        df,
        ["municipality_name", "ADM2_NAME", "shapeName", "NAME_2", "adm2_name", "municipio"],
    )
    dept_col = first_existing_column(
        df,
        ["department_name", "ADM1_NAME", "shapeGroup", "NAME_1", "adm1_name", "departamento"],
    )
    country_col = first_existing_column(
        df,
        ["country_name", "ADM0_NAME", "shapeGroup", "NAME_0", "adm0_name", "country"],
    )
    if "municipality_name" not in df.columns and name_col is not None:
        df["municipality_name"] = df[name_col].astype(str)
    if "department_name" not in df.columns and dept_col is not None:
        df["department_name"] = df[dept_col].astype(str)
    if "country_name" not in df.columns and country_col is not None:
        df["country_name"] = df[country_col].astype(str)
    if "muni_name_norm" not in df.columns:
        base = df["municipality_name"] if "municipality_name" in df.columns else pd.Series("", index=df.index)
        df["muni_name_norm"] = base.map(normalize_text)
    if "dept_name_norm" not in df.columns:
        base = df["department_name"] if "department_name" in df.columns else pd.Series("", index=df.index)
        df["dept_name_norm"] = base.map(normalize_text)
    if "country_name_norm" not in df.columns:
        base = df["country_name"] if "country_name" in df.columns else pd.Series("", index=df.index)
        df["country_name_norm"] = base.map(normalize_text)
    return df


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, low_memory=False)
    if suffix in {".dta", ".stata"}:
        return pd.read_stata(path)
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported table type: {path}")


def write_json(path: str | Path, payload: object) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def zscore(series: pd.Series) -> pd.Series:
    vals = to_numeric(series)
    std = vals.std(skipna=True)
    if std is None or math.isclose(float(std), 0.0) or pd.isna(std):
        return pd.Series(np.nan, index=series.index)
    return (vals - vals.mean(skipna=True)) / std


def safe_bool_int(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.astype(int)
    return series.fillna(0).astype(float).gt(0).astype(int)
