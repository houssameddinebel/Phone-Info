# PhoneInfo

Offline-first phone-number intelligence, with optional carrier-API enrichment.

## What it actually gives you

| Data | Source | Reliability |
|---|---|---|
| Country + country calling code | number itself | exact |
| Valid / possible | libphonenumber rules | exact |
| Canonical formats (E.164, RFC3966, national) | number itself | exact |
| Original prefix region/city (fixed lines) | libphonenumber prefix DB | good for landlines, **often wrong for mobiles** |
| Carrier (from prefix) | libphonenumber prefix DB | stale; ignores portability |
| Line type (mobile / fixed / VoIP / toll-free) | libphonenumber rules | good |
| Timezones for the region | tz DB | region-level only |
| Current carrier, ported status, MCC/MNC, caller name | optional paid APIs | good, still not location |

## What it cannot give you

**The live location of a phone.** No number-only tool can. Specifically:

- A mobile prefix maps to where the number block was *issued*, not where the handset is. Portability breaks even that.
- Carrier HLR/HLR-lookup services return the *serving network's* coarse region and MCC/MNC — a network-level attribute, not a device position.
- Real position comes only from: the handset reporting it (E911 / AML, Find My, a consenting app), or carrier lawful intercept with a legal order. Anything else advertised as "phone number tracker" is a scam, spyware, or SS7 abuse.

So treat "prefix region" as *the region the number belongs to*, never as *where the person is*.

## Install

```powershell
pip install -r phoneinfo/requirements.txt
```

## Usage

```powershell
# single number
python -m phoneinfo "+14155552671"

# local format + default region
python -m phoneinfo "02071838750" -r GB

# many numbers from a file (one per line, # comments allowed)
python -m phoneinfo -f demo_numbers.txt

# machine-readable
python -m phoneinfo "+14155552671" --json

# mask digits (for reports / logs)
python -m phoneinfo "+14155552671" --redact
```

## Optional carrier enrichment

Set the env vars for whichever provider(s) you have, then run with `-p`:

```powershell
$env:VERIPHONE_KEY = "..."
python -m phoneinfo "+14155552671" -p veriphone
python -m phoneinfo -f demo_numbers.txt -p numverify,twilio
python -m phoneinfo "+14155552671" -p all
```

| provider | env vars |
|---|---|
| `numverify` | `NUMVERIFY_KEY` |
| `veriphone` | `VERIPHONE_KEY` |
| `twilio` | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` |
| `abstractapi` | `ABSTRACTAPI_PHONE_KEY` |

Providers without credentials are skipped, not failed. Add your own in
`phoneinfo/providers.py` — implement `fn(number, region) -> dict` and register it.

## Library use

```python
from phoneinfo import analyze, enrich

info = analyze("+919876543210")
print(info["country_name"], info["prefix_location"], info["line_type"])

extra = enrich(info["e164"], providers=["veriphone"])
```

## Legal note

Lookups of numbers you own or have consent to handle are routine. Aggregating
location/identity data about a person without authorization is a criminal
offense in most jurisdictions (stalking / unlawful tracking). The tool prints
the prefix region and nothing more; it is not a tracker.
