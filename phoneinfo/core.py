"""
Offline phone-number intelligence.

Everything in this module runs with no network access. It resolves what is
*derivable from the number itself*: country, issuing region, original prefix
geography, carrier, line type, and timezone.

It does NOT and cannot resolve the live location of a handset. See README.
"""

from __future__ import annotations

from typing import Any

import phonenumbers
from phonenumbers import carrier, geocoder, number_type, timezone

from . import mnc

# libphonenumber's timezone map has a couple of entries that disagree with the
# IANA tz database. Morocco has been on UTC+01 permanently since 2018
# (Africa/Casablanca), but the metadata resolves it to the Canary Islands.
_TZ_OVERRIDE: dict[str, list[str]] = {
    "MA": ["Africa/Casablanca"],
}

# phonenumbers line-type constants -> human labels
_TYPE_LABELS: dict[int, str] = {
    phonenumbers.PhoneNumberType.FIXED_LINE: "fixed_line",
    phonenumbers.PhoneNumberType.MOBILE: "mobile",
    phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE: "fixed_line_or_mobile",
    phonenumbers.PhoneNumberType.TOLL_FREE: "toll_free",
    phonenumbers.PhoneNumberType.PREMIUM_RATE: "premium_rate",
    phonenumbers.PhoneNumberType.SHARED_COST: "shared_cost",
    phonenumbers.PhoneNumberType.VOIP: "voip",
    phonenumbers.PhoneNumberType.PERSONAL_NUMBER: "personal_number",
    phonenumbers.PhoneNumberType.PAGER: "pager",
    phonenumbers.PhoneNumberType.UAN: "uan",
    phonenumbers.PhoneNumberType.VOICEMAIL: "voicemail",
    phonenumbers.PhoneNumberType.UNKNOWN: "unknown",
}


class InvalidNumber(ValueError):
    """Raised when the input cannot be parsed as a phone number at all."""


def analyze(raw: str, default_region: str | None = None, lang: str = "en") -> dict[str, Any]:
    """
    Parse `raw` and return everything derivable offline.

    `default_region` is an ISO-3166 alpha-2 code (e.g. "US", "GB") used to
    interpret numbers that are not in international (+country) form.
    """
    raw = (raw or "").strip()
    if not raw:
        raise InvalidNumber("empty input")

    try:
        num = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException as exc:
        if exc.error_type == phonenumbers.NumberParseException.INVALID_COUNTRY_CODE:
            raise InvalidNumber(
                "no country code and no default region given — this looks like a "
                "local number, so pick a default region (MA for Morocco, FR for "
                "France, and so on)"
            ) from exc
        raise InvalidNumber(str(exc)) from exc

    region_code = phonenumbers.region_code_for_number(num)
    country_code = num.country_code
    ntype = number_type(num)

    # The geocoder only yields a country name when it has a geographic
    # description, which it lacks for most mobile ranges. Fall back to the
    # MCC/MNC table keyed on the region code.
    country_name = (
        geocoder.country_name_for_number(num, lang)
        or mnc.country_name(region_code)
    )

    zones = _TZ_OVERRIDE.get(region_code or "") or list(
        timezone.time_zones_for_number(num) or ()
    )

    result: dict[str, Any] = {
        "input": raw,
        "valid": phonenumbers.is_valid_number(num),
        "possible": phonenumbers.is_possible_number(num),
        "e164": phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164),
        "international": phonenumbers.format_number(
            num, phonenumbers.PhoneNumberFormat.INTERNATIONAL
        ),
        "national": phonenumbers.format_number(
            num, phonenumbers.PhoneNumberFormat.NATIONAL
        ),
        "rfc3966": phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.RFC3966),
        "country_code": country_code,
        "region_code": region_code,
        "country_name": country_name,
        "mcc": mnc.mcc_for_region(region_code),
        # "location" here is the ORIGINAL prefix geography, not where the phone is now.
        "prefix_location": geocoder.description_for_number(num, lang) or None,
        # Allocated from the national numbering plan. NOT the current carrier
        # wherever number portability exists.
        "allocated_carrier": carrier.name_for_number(num, lang) or None,
        "line_type": _TYPE_LABELS.get(ntype, "unknown"),
        "line_type_id": ntype,
        "is_geographical": phonenumbers.is_number_geographical(num),
        "timezones": zones,
        "networks_in_country": mnc.networks(region_code),
    }
    return result


def batch(numbers: list[str], default_region: str | None = None, lang: str = "en") -> list[dict[str, Any]]:
    """Analyze many numbers, capturing per-number errors inline."""
    out: list[dict[str, Any]] = []
    for item in numbers:
        try:
            out.append(analyze(item, default_region=default_region, lang=lang))
        except InvalidNumber as exc:
            out.append({"input": item, "valid": False, "error": f"unparseable: {exc}"})
    return out


def candidates(raw: str, limit: int = 40) -> list[dict[str, Any]]:
    """
    Countries in which `raw` would be a valid number.

    A local number carries no country code, so several countries can legitimately
    claim it. This returns all of them so the caller can pick, rather than
    guessing a region and presenting a confident wrong answer.
    """
    out: list[dict[str, Any]] = []
    for region in sorted(phonenumbers.SUPPORTED_REGIONS):
        try:
            num = phonenumbers.parse(raw, region)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(num):
            out.append(
                {
                    "region": region,
                    "country": mnc.country_name(region) or region,
                    "e164": phonenumbers.format_number(num, phonenumbers.PhoneNumberFormat.E164),
                    "international": phonenumbers.format_number(
                        num, phonenumbers.PhoneNumberFormat.INTERNATIONAL
                    ),
                }
            )
    out.sort(key=lambda c: (c["country"] == c["region"], c["country"].lower(), c["region"]))
    return out[:limit]


def redact(entry: dict[str, Any], keep: int = 4) -> dict[str, Any]:
    """Mask all but the last `keep` digits of the E.164 form. For logs/reports."""
    out = dict(entry)
    e164 = out.get("e164")
    if isinstance(e164, str) and len(e164) > keep:
        out["e164"] = "*" * (len(e164) - keep) + e164[-keep:]
        out["international"] = out["e164"]
        out["national"] = out["e164"]
    return out
