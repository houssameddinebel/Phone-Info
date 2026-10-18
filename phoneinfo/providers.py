"""
Optional network providers for carrier / line-type enrichment.

These add data the offline engine cannot know: the *current* carrier (after
number portability), ported status, and the carrier's own coarse registration
region. They still do not give handset location.

Every provider is optional. A provider whose credentials are absent is skipped.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

import requests

TIMEOUT = 15


class ProviderError(RuntimeError):
    pass


@dataclass
class Provider:
    name: str
    env_keys: tuple[str, ...]
    fn: Callable[[str, str | None], dict[str, Any]]

    def available(self) -> bool:
        return all(os.environ.get(k) for k in self.env_keys)

    def explain_missing(self) -> str:
        return "missing env: " + ", ".join(k for k in self.env_keys if not os.environ.get(k))


def _get(url: str, **kwargs: Any) -> dict[str, Any]:
    try:
        resp = requests.get(url, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise ProviderError(f"request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise ProviderError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except ValueError as exc:
        raise ProviderError("non-JSON response") from exc


# --- Numverify (apilayer) ---------------------------------------------------
# https://numverify.com/documentation
def _numverify(number: str, region: str | None) -> dict[str, Any]:
    key = os.environ["NUMVERIFY_KEY"]
    params = {"access_key": key, "number": number, "format": 1}
    if region:
        params["country_code"] = region
    data = _get("http://apilayer.net/api/validate", params=params)
    if data.get("success") is False:
        err = data.get("error") or {}
        raise ProviderError(err.get("info") or err.get("type") or "unknown error")
    return {
        "valid": data.get("valid"),
        "country": data.get("country_name"),
        "location": data.get("location"),
        "carrier": data.get("carrier"),
        "line_type": data.get("line_type"),
    }


# --- Veriphone --------------------------------------------------------------
# https://veriphone.io/docs/v2
def _veriphone(number: str, region: str | None) -> dict[str, Any]:
    key = os.environ["VERIPHONE_KEY"]
    params = {"phone": number, "key": key, "default_country": region or "US"}
    data = _get("https://api.veriphone.io/v2/verify", params=params)
    if data.get("status") not in (None, "success"):
        raise ProviderError(str(data.get("status")))
    return {
        "valid": data.get("phone_valid"),
        "country": data.get("country"),
        "location": data.get("phone_region"),
        "carrier": data.get("carrier"),
        "line_type": data.get("phone_type"),
    }


# --- Twilio Lookup v2 -------------------------------------------------------
# https://www.twilio.com/docs/lookup/v2-api
def _twilio(number: str, region: str | None) -> dict[str, Any]:
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    url = f"https://lookups.twilio.com/v2/PhoneNumbers/{requests.utils.quote(number, safe='')}"
    params: dict[str, str] = {"Fields": "line_type_intelligence,caller_name"}
    if region:
        params["CountryCode"] = region
    data = _get(url, params=params, auth=(sid, token))
    lti = data.get("line_type_intelligence") or {}
    caller = data.get("caller_name") or {}
    return {
        "valid": data.get("valid"),
        "country": data.get("country_code"),
        "location": lti.get("mobile_country_code") and f"MCC {lti['mobile_country_code']}",
        "carrier": lti.get("carrier_name"),
        "line_type": lti.get("type"),
        "ported": lti.get("carrier_name") is not None,
        "caller_name": caller.get("caller_name"),
    }


# --- AbstractAPI ------------------------------------------------------------
# https://www.abstractapi.com/api/phone-validation-api
def _abstractapi(number: str, region: str | None) -> dict[str, Any]:
    key = os.environ["ABSTRACTAPI_PHONE_KEY"]
    params = {"api_key": key, "phone": number}
    if region:
        params["country"] = region
    data = _get("https://phonevalidation.abstractapi.com/v1/", params=params)
    if data.get("error"):
        raise ProviderError(str(data["error"]))
    return {
        "valid": data.get("valid"),
        "country": (data.get("country") or {}).get("name"),
        "location": data.get("location"),
        "carrier": data.get("carrier"),
        "line_type": data.get("type"),
    }


REGISTRY: dict[str, Provider] = {
    "numverify": Provider("numverify", ("NUMVERIFY_KEY",), _numverify),
    "veriphone": Provider("veriphone", ("VERIPHONE_KEY",), _veriphone),
    "twilio": Provider("twilio", ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"), _twilio),
    "abstractapi": Provider("abstractapi", ("ABSTRACTAPI_PHONE_KEY",), _abstractapi),
}


def enrich(
    number: str,
    region: str | None = None,
    providers: list[str] | None = None,
) -> dict[str, Any]:
    """
    Run the requested providers against `number`.

    Returns {"results": {provider: payload}, "errors": {provider: message},
             "skipped": {provider: reason}}.
    """
    names = providers or list(REGISTRY)
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    skipped: dict[str, str] = {}

    for name in names:
        prov = REGISTRY.get(name)
        if prov is None:
            errors[name] = "unknown provider"
            continue
        if not prov.available():
            skipped[name] = prov.explain_missing()
            continue
        try:
            results[name] = prov.fn(number, region)
        except ProviderError as exc:
            errors[name] = str(exc)

    return {"results": results, "errors": errors, "skipped": skipped}
