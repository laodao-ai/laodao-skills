#!/usr/bin/env python3
"""Check domain availability across TLDs, reliably, for brand/product naming.

Method (hybrid — each part covers the other's blind spot):

  * RDAP over HTTPS (rdap.org bootstrap -> authoritative registry):
      200 -> registered (TAKEN), always trustworthy.
      404 -> "not found" — BUT ambiguous: it also means "this TLD isn't in the
             RDAP bootstrap" (e.g. .io: every .io returns 404, so RDAP alone
             would mark all of them FREE — a silent, dangerous false-positive).
  * whois (port 43) — used to disambiguate a 404 for ccTLDs. Reliable for .io,
    .com, etc. for *availability*, but on macOS `whois name.dev` only reaches the
    IANA TLD record, so it cannot judge .dev — which is exactly why we trust
    RDAP for gTLDs and only fall back to whois for the rest.

Decision per domain:
  RDAP 200                                  -> TAKEN
  RDAP 404 and TLD is RDAP-reliable (gTLD)  -> FREE
  RDAP 404 and TLD is a ccTLD/other         -> whois decides (markers below)
  RDAP error/timeout                        -> whois decides, else '?'

Usage:
  check_domains.py NAME [NAME ...] [--tlds com,dev,io] [--json] [--timeout 20]
"""
import argparse
import json
import re
import subprocess
import urllib.error
import urllib.request

# gTLDs we have verified rdap.org covers cleanly (404 == genuinely available).
# For anything else (.io, .sh, .co, .ai, ccTLDs ...) a 404 is ambiguous and we
# confirm with whois.
RDAP_RELIABLE_TLDS = {"com", "net", "org", "info", "dev", "app", "page", "build"}

WHOIS_FREE = re.compile(
    r"no match|not found|no entries found|no data found|"
    r"status:\s*(free|available)|available for (registration|purchase)",
    re.I,
)
WHOIS_TAKEN = re.compile(
    r"creation date|created:|registry expiry|registrar:|registrant|"
    r"name server|nserver|domain status",
    re.I,
)


def rdap_code(domain, timeout):
    """Return the HTTP status from the authoritative RDAP server, or None."""
    url = "https://rdap.org/domain/" + domain
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "domain-check/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode()
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def whois_status(domain):
    """Return 'FREE', 'TAKEN', or None (inconclusive) from port-43 whois."""
    try:
        out = subprocess.run(
            ["whois", domain], capture_output=True, text=True, timeout=25
        ).stdout
    except Exception:
        return None
    # Check "available" markers first: a free domain's record may still echo the
    # queried name, so a taken-marker substring match alone is not enough.
    if WHOIS_FREE.search(out):
        return "FREE"
    if WHOIS_TAKEN.search(out):
        return "TAKEN"
    return None


def check(domain, timeout):
    tld = domain.rsplit(".", 1)[-1].lower()
    code = rdap_code(domain, timeout)
    if code == 200:
        return "TAKEN"
    if code == 404:
        if tld in RDAP_RELIABLE_TLDS:
            return "FREE"
        # ambiguous (e.g. .io): RDAP doesn't cover the TLD -> ask whois
        return whois_status(domain) or "FREE"
    # RDAP error/timeout -> whois, else unknown
    return whois_status(domain) or "?"


def main():
    ap = argparse.ArgumentParser(description="Check domain availability (RDAP + whois).")
    ap.add_argument("names", nargs="+", help="Base names without TLD (e.g. sarvelo).")
    ap.add_argument("--tlds", default="com,dev,io", help="Comma-separated TLDs.")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    ap.add_argument("--timeout", type=int, default=20, help="Per-request timeout (s).")
    args = ap.parse_args()

    tlds = [t.strip().lstrip(".") for t in args.tlds.split(",") if t.strip()]
    results = {}
    for name in args.names:
        name = name.strip().lower()
        results[name] = {t: check("{}.{}".format(name, t), args.timeout) for t in tlds}

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print("| name | " + " | ".join("." + t for t in tlds) + " |")
    print("|---|" + "---|" * len(tlds))
    for name, row in results.items():
        print("| {} | {} |".format(name, " | ".join(row[t] for t in tlds)))


if __name__ == "__main__":
    main()
