"""
Build the vendored MCC/MNC reference table.

Source: pbakondy/mcc-mnc-list (community-maintained, compiled from ITU-T E.212
operational bulletins and GSMA data). We keep only the fields the tool needs.

    python tools/build_mnc.py
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

URL = "https://raw.githubusercontent.com/pbakondy/mcc-mnc-list/master/mcc-mnc-list.json"
OUT = Path(__file__).resolve().parent.parent / "data" / "mnc.json"
KEEP = ("mcc", "mnc", "countryName", "countryCode", "brand", "operator", "status", "bands")


def main() -> None:
    raw = urllib.request.urlopen(URL, timeout=60).read().decode("utf-8", "replace")
    entries = json.loads(raw)

    slim = [
        {
            "mcc": e.get("mcc"),
            "mnc": e.get("mnc"),
            "country": e.get("countryName"),
            "iso": e.get("countryCode"),
            "brand": e.get("brand") or None,
            "operator": e.get("operator") or None,
            "status": e.get("status"),
            "bands": e.get("bands") or None,
        }
        for e in entries
    ]

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(slim, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({len(slim)} entries, {OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
