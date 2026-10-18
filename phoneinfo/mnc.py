"""
MCC / MNC reference lookups, backed by the vendored table in data/mnc.json.

MCC (Mobile Country Code) and MNC (Mobile Network Code) together form the PLMN
that identifies a *network* — defined in ITU-T E.212. This module answers the
questions you can answer offline:

  - which MCC belongs to a country
  - which operators exist in a country, and under which MNCs
  - what a given PLMN (604-01) resolves to

It cannot tell you which network a specific number is currently on. That
requires a live HLR/network query, because the number alone does not carry it.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_DATA = Path(__file__).parent / "data" / "mnc.json"

# Live networks first, then everything else, so the UI leads with real carriers.
_STATUS_RANK = {
    "Operational": 0,
    "Allocated": 1,
    "Unknown": 2,
    "Reserved": 3,
    "Returned spare": 4,
    "Not operational": 5,
}


@lru_cache(maxsize=1)
def _table() -> list[dict[str, Any]]:
    if not _DATA.is_file():
        return []
    return json.loads(_DATA.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _by_iso() -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for row in _table():
        iso = (row.get("iso") or "").split("-")[0].upper()
        if iso:
            out.setdefault(iso, []).append(row)
    return out


def _rows_for(region: str) -> list[dict[str, Any]]:
    """
    Rows for an ISO region code.

    Prefers exact ISO matches so that sub-national entries (Abkhazia is 'GE-AB')
    do not leak into their parent country's name or MCC. Falls back to the
    prefix map for regions that only appear in the extended form.
    """
    region = region.upper()
    exact = [r for r in _table() if (r.get("iso") or "").upper() == region]
    return exact or _by_iso().get(region, [])


def country_name(region: str | None) -> str | None:
    """Country name for an ISO-3166 alpha-2 region code, or None."""
    if not region:
        return None
    rows = _rows_for(region)
    counts: dict[str, int] = {}
    for r in rows:
        name = r.get("country")
        if name:
            counts[name] = counts.get(name, 0) + 1
    return max(counts, key=counts.get) if counts else None


def mcc_for_region(region: str | None) -> str | None:
    """The MCC assigned to a country. Exact and offline."""
    if not region:
        return None
    rows = _rows_for(region)
    if not rows:
        return None
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["mcc"]] = counts.get(r["mcc"], 0) + 1
    return max(counts, key=counts.get)


def lookup(mcc: str, mnc: str) -> dict[str, Any] | None:
    """Resolve a PLMN such as ('604', '01') to its network record."""
    for row in _table():
        if row["mcc"] == str(mcc) and row["mnc"].zfill(2) == str(mnc).zfill(2):
            return row
    return None


def networks(region: str | None) -> list[dict[str, Any]]:
    """
    Every registered network in a country, one entry per brand, with all of its
    MNCs collected. Sorted operational-first.
    """
    if not region:
        return []

    grouped: dict[str, dict[str, Any]] = {}
    for row in _by_iso().get(region.upper(), []):
        key = (row.get("brand") or row.get("operator") or "?").strip()
        entry = grouped.setdefault(
            key,
            {
                "brand": key,
                "operator": row.get("operator"),
                "mncs": [],
                "status": row.get("status"),
                "bands": row.get("bands"),
            },
        )
        entry["mncs"].append(row["mnc"])
        # Keep the strongest status seen for the brand, and the richest band set.
        if _STATUS_RANK.get(row.get("status"), 9) < _STATUS_RANK.get(entry["status"], 9):
            entry["status"] = row.get("status")
        if row.get("bands") and (
            not entry["bands"] or entry["bands"] == "Unknown"
            or len(row["bands"]) > len(entry["bands"])
        ):
            entry["bands"] = row.get("bands")

    result = []
    for entry in grouped.values():
        entry["mncs"] = sorted(set(entry["mncs"]))
        entry["plmns"] = [f"{mcc_for_region(region)}-{m}" for m in entry["mncs"]]
        result.append(entry)
    result.sort(key=lambda e: (_STATUS_RANK.get(e["status"], 9), e["brand"]))
    return result
