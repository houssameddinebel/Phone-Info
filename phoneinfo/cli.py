"""Command-line interface for phoneinfo."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import core, providers


def _collect_numbers(args: argparse.Namespace) -> list[str]:
    nums: list[str] = list(args.numbers or [])
    if args.file:
        # utf-8-sig strips a BOM that Windows editors like to prepend.
        with open(args.file, "r", encoding="utf-8-sig") as fh:
            for line in fh:
                line = line.split("#", 1)[0].strip().lstrip("\ufeff")
                if line:
                    nums.append(line)
    return nums


def _print_report(entry: dict[str, Any], enrich: dict[str, Any] | None) -> None:
    if entry.get("error"):
        print(f"  ! {entry['input']}: {entry['error']}\n")
        return

    print(f"  input            {entry['input']}")
    print(f"  e164             {entry['e164']}")
    print(f"  international    {entry['international']}")
    print(f"  valid / possible {entry['valid']} / {entry['possible']}")
    print(f"  country          {entry['country_name']} ({entry['region_code']}, +{entry['country_code']})")
    print(f"  mcc              {entry['mcc'] or '-'}")
    print(f"  prefix region    {entry['prefix_location'] or '-'}")
    print(f"  allocated to     {entry['allocated_carrier'] or '-'}")
    print(f"  line type        {entry['line_type']}")
    print(f"  timezones        {', '.join(entry['timezones']) or '-'}")

    nets = entry.get("networks_in_country") or []
    if nets:
        print(f"  networks in country ({len(nets)}):")
        for n in nets:
            plmns = ",".join(n["plmns"])
            print(f"     {n['brand']:<22} {plmns:<16} {n['status']}")

    if enrich:
        for name, payload in enrich["results"].items():
            print(f"  -- {name} --")
            for k, v in payload.items():
                print(f"     {k:<14} {v}")
        for name, msg in enrich["errors"].items():
            print(f"  -- {name}: error: {msg}")
        for name, msg in enrich["skipped"].items():
            print(f"  -- {name}: skipped ({msg})")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="phoneinfo",
        description="Offline phone-number intelligence (country, prefix region, carrier, line type).",
    )
    parser.add_argument("numbers", nargs="*", help="numbers to analyze, e.g. +14155552671")
    parser.add_argument("-f", "--file", help="file with one number per line (# comments allowed)")
    parser.add_argument("-r", "--region", help="default ISO region for numbers without +, e.g. US")
    parser.add_argument("-l", "--lang", default="en", help="language for region/carrier names (default: en)")
    parser.add_argument(
        "-p",
        "--providers",
        default="none",
        help="comma-separated enrichment providers, or 'all' (numverify,veriphone,twilio,abstractapi)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    parser.add_argument("--redact", action="store_true", help="mask digits in output (for reports/logs)")
    parser.add_argument(
        "--serve",
        nargs="?",
        const="8765",
        metavar="PORT",
        help="run the local web UI instead of a lookup (default port 8765)",
    )
    args = parser.parse_args(argv)

    if args.serve is not None:
        from .server import serve

        try:
            port = int(args.serve)
        except ValueError:
            parser.error(f"--serve wants a port number, got {args.serve!r}")
        serve(port=port)
        return 0

    # Windows consoles default to cp1252; region/carrier names may need more.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    numbers = _collect_numbers(args)
    if not numbers:
        parser.error("no numbers given (pass positionally or with --file)")

    if args.providers.strip().lower() in ("none", ""):
        requested: list[str] = []
    elif args.providers.strip().lower() == "all":
        requested = list(providers.REGISTRY)
    else:
        requested = [p.strip() for p in args.providers.split(",") if p.strip()]

    records: list[dict[str, Any]] = []
    for raw in numbers:
        try:
            entry = core.analyze(raw, default_region=args.region, lang=args.lang)
        except core.InvalidNumber as exc:
            entry = {"input": raw, "valid": False, "error": f"unparseable: {exc}"}

        enrich = None
        if requested and entry.get("valid"):
            enrich = providers.enrich(entry["e164"], region=args.region, providers=requested)

        if args.redact and not entry.get("error"):
            entry = core.redact(entry)

        if args.json:
            rec = dict(entry)
            if enrich:
                rec["enrichment"] = enrich
            records.append(rec)
        else:
            _print_report(entry, enrich)

    if args.json:
        json.dump(records[0] if len(records) == 1 else records, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
