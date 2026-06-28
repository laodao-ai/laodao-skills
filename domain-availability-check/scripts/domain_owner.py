#!/usr/bin/env python3
"""Recon a (usually TAKEN) domain: who holds it and what industry.

A free domain on one TLD does NOT clear a name. If an *adjacent* software/tech
company holds another TLD, the name carries trademark (Class 9/42) and
search/SEO risk even though your preferred TLD is open (the "Abilo lesson").
This script surfaces the facts needed for that adjacency judgment:

  - whois highlights: registrar, creation date (age signal), nameservers
    (host/country hint), registrant org (often privacy-redacted)
  - the live site's <title> + meta description (what the holder actually does)

Usage:
  domain_owner.py DOMAIN [DOMAIN ...]      # full domains, e.g. abilo.com abilo.io
"""
import re
import subprocess
import sys
import urllib.request

WHOIS_KEYS = (
    "registrar:", "creation date", "created:", "registrant organization",
    "registrant name", "name server", "registrant country", "registry expiry",
)


def whois_summary(domain):
    try:
        out = subprocess.run(
            ["whois", domain], capture_output=True, text=True, timeout=25
        ).stdout
    except Exception as e:  # whois missing, blocked, or timed out
        return ["(whois unavailable: {})".format(e)]
    lines = []
    for raw in out.splitlines():
        s = raw.strip()
        if s and any(k in s.lower() for k in WHOIS_KEYS) and s not in lines:
            lines.append(s)
    return lines[:14] or ["(no whois fields parsed)"]


def site_sniff(domain):
    for scheme in ("https://", "http://"):
        try:
            req = urllib.request.Request(
                scheme + domain, headers={"User-Agent": "Mozilla/5.0"}
            )
            html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore")
        except Exception:
            continue
        title = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        desc = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            html, re.I | re.S,
        )
        t = title.group(1).strip() if title else "(no <title>)"
        out = "title: " + re.sub(r"\s+", " ", t)
        if desc:
            out += "\n  desc:  " + re.sub(r"\s+", " ", desc.group(1).strip())
        return out
    return "(site did not respond — may be parked or unhosted)"


def main():
    if len(sys.argv) < 2:
        print("usage: domain_owner.py DOMAIN [DOMAIN ...]")
        sys.exit(1)
    for domain in sys.argv[1:]:
        print("\n===== {} =====".format(domain))
        print("WHOIS:")
        for line in whois_summary(domain):
            print("  " + line)
        print("SITE:")
        print("  " + site_sniff(domain).replace("\n", "\n  "))


if __name__ == "__main__":
    main()
