"""
Local web UI for phoneinfo.

Stdlib only (plus phonenumbers via the core engine). Binds to 127.0.0.1 so it
is not reachable from the network.

    python -m phoneinfo --serve          # http://127.0.0.1:8765
    python -m phoneinfo --serve 9000
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import phonenumbers

from . import core, mnc, providers

WEB_DIR = Path(__file__).parent / "web"

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
}

_regions_cache: list[dict[str, str]] | None = None


def _regions() -> list[dict[str, str]]:
    """Every ISO region libphonenumber supports, with a human-readable name."""
    global _regions_cache
    if _regions_cache is None:
        items = [
            {"code": code, "name": mnc.country_name(code) or code}
            for code in sorted(phonenumbers.SUPPORTED_REGIONS)
            if len(code) == 2 and code.isalpha()
        ]
        # Named countries first (alphabetical), then codes we have no name for.
        items.sort(key=lambda i: (i["name"] == i["code"], i["name"].lower(), i["code"]))
        _regions_cache = items
    return _regions_cache


def _lookup(query: dict[str, list[str]]) -> tuple[int, dict]:
    raw = (query.get("number") or [""])[0].strip()
    region = (query.get("region") or [""])[0].strip().upper() or None
    prov = (query.get("providers") or ["none"])[0].strip().lower()

    if not raw:
        return 400, {"error": "no number supplied"}

    if prov in ("", "none"):
        requested: list[str] = []
    elif prov == "all":
        requested = list(providers.REGISTRY)
    else:
        requested = [p.strip() for p in prov.split(",") if p.strip()]

    try:
        entry = core.analyze(raw, default_region=region)
    except core.InvalidNumber as exc:
        payload: dict = {"input": raw, "valid": False, "error": str(exc)}
        # A local number is valid in many countries; offer them instead of
        # guessing one and reporting a confident wrong answer.
        if not region:
            cands = core.candidates(raw)
            if cands:
                payload["candidates"] = cands
        return 200, payload

    # A number without "+" was interpreted through the default region. Say so,
    # and offer the alternatives, rather than letting the choice happen silently.
    if region and not raw.startswith("+"):
        entry["assumed_region"] = region
        entry["candidates"] = core.candidates(raw)

    if requested and entry["valid"]:
        entry["enrichment"] = providers.enrich(entry["e164"], region=region, providers=requested)
    elif requested:
        entry["enrichment"] = {
            "results": {},
            "errors": {},
            "skipped": {p: "number is not valid, skipped" for p in requested},
        }
    return 200, entry


class Handler(BaseHTTPRequestHandler):
    server_version = "phoneinfo/0.3"

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        print(f"  {self.address_string()} {fmt % args}")

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, rel: str) -> None:
        target = (WEB_DIR / rel).resolve()
        if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
            self._send_json(404, {"error": "not found"})
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _MIME.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/lookup":
            status, payload = _lookup(parse_qs(parsed.query))
            self._send_json(status, payload)
            return
        if parsed.path == "/api/regions":
            self._send_json(200, {"regions": _regions()})
            return
        if parsed.path in ("/", "/index.html"):
            self._send_file("index.html")
            return
        self._send_file(parsed.path.lstrip("/"))


def serve(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"phoneinfo web UI running at {url}")
    print("Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
