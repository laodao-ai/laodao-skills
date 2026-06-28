---
name: domain-availability-check
description: Check domain availability across .com/.dev/.io (and any TLD) and find out who owns the taken ones, for brand/product naming and clearance. Use whenever the user is checking domains, picking or vetting a brand/product/repo name, asks "域名可用吗"/"查一下域名"/"谁占了 X.com"/"is this name taken"/"who owns this domain"/"domain availability", or right after generating candidate names to filter by what is actually registerable. Also use before registering a domain, GitHub org, npm scope, or launching a product. Companion to trademark-basic-search (run that for the legal side). Prefer this skill over ad-hoc whois — it encodes the reliable method so you don't re-derive it each time.
---

# Domain Availability Check

Naming work keeps hitting the same wall: you generate a great short name and every domain is already taken. Each time, people re-derive *how* to reliably check availability and *how* to find who holds a taken domain. This skill encodes that method so it is one command, not a research session.

It does two things:
1. **Availability matrix** — is `name.{com,dev,io,...}` registerable, fast and reliably.
2. **Ownership recon** — for a taken domain you care about, who holds it and *what industry* — because that determines whether the name is a trademark/brand risk, not just a domain inconvenience.

This is basic screening, **not** legal clearance. For trademarks, pair with the **`trademark-basic-search`** skill.

## Core method: hybrid RDAP + whois (each covers the other's blind spot)

`scripts/check_domains.py` does this for you — but understand *why* it is hybrid, because neither tool alone is correct:

- **Plain `whois` is unreliable** in sandboxed/agent environments: port 43 is often blocked (returns nothing → looks "available" when it is not), and on macOS `whois name.dev` only reaches the **IANA TLD record** ("domain: DEV", Charleston Road Registry) for *both* free and taken `.dev` — it cannot judge `.dev` at all.
- **Plain RDAP is unreliable too**, in a subtler, more dangerous way: via the `rdap.org` bootstrap, `200 = registered` is always trustworthy, but **`404` is ambiguous** — it means "not found" *or* "this TLD isn't in the RDAP bootstrap." `.io` is the trap: **every** `.io` returns 404 (verified: `google.io`, `github.io` both 404), so RDAP alone marks all `.io` FREE — a silent false-positive.

So the script combines them:

| Signal | Verdict |
|---|---|
| RDAP `200` | TAKEN (always) |
| RDAP `404`, gTLD (`.com/.dev/.app`…) | FREE |
| RDAP `404`, ccTLD/other (`.io/.sh/.co`…) | whois decides (it covers `.io` fine) |
| RDAP error/timeout | whois decides, else `?` (rerun) |

`whois` is also the right tool for *ownership* recon (registrant, age, nameservers) once a domain is taken — that is what `scripts/domain_owner.py` uses.

## Workflow

### 1. Availability matrix

```bash
python3 scripts/check_domains.py sarvelo vornelo korvelo --tlds com,dev,io
```

Output is a markdown matrix of `FREE` / `TAKEN` / `?` (unknown — timeout, retried once; rerun if seen). Add `--json` for machine-readable output, `--tlds com,dev,io,sh,app` for more TLDs.

**Reading the result for dev-tools naming:**
- `.com` is almost always `TAKEN` for any pronounceable name — domain investors hold them all, short *and* coined. Don't treat `.com` taken as fatal by itself.
- A clean `.dev` (and/or `.io`) is the realistic win. `.dev` is fully accepted for developer-tools brands (zed.dev, bun.sh, fly.io). Enterprise/non-dev audiences still type `.com`, so for those lines plan a `getX.com` fallback or buy the `.com`.

### 2. Ownership recon (for taken names you still like)

A free domain on one TLD does **not** clear a name. Find out who holds the other TLDs:

```bash
python3 scripts/domain_owner.py abilo.com abilo.io
```

It prints whois highlights (registrar, creation date = age signal, nameservers = host/country hint, registrant org — often privacy-redacted) **and the live site's title + description** (what the holder actually does).

**The judgment that matters — adjacency:**
- Holder is an **adjacent software / SaaS / tech company** → red flag. Same trademark classes (9/42), poisoned search/SEO, traffic leak. **Drop the name even if another TLD is free.**
- Holder is a **parked page / unrelated industry / pure squatter** → lower risk; the `.dev`/`.io` route is viable, or you can try to buy the `.com`.

> **The Abilo lesson** (why this step exists): `abilo.dev` was free, but `abilo.com` was a live construction-ERP **SaaS** and `abilo.io` was another "Abilo" app. Adjacent software in the same classes → the free `.dev` could not save the name. Always run recon before committing.

### 3. Decision framework

The **naming trilemma** — short / meaningful-recognizable / available — gives you at most two:
- short + meaningful → domain taken (the usual wall);
- short + available → must be an invented/coined word (sacrifice initial meaning);
- meaningful + available → must be longer or compound.

So when availability keeps failing, the fix is to *deliberately move corner* (go coined, or go longer/compound), not to keep checking more TLDs for the same short-meaningful name. Coined names that actually have room are typically **6–8 letters / 3 syllables** (Vercel, Twilio, Heroku, Pulumi); 4–5 letter coined strings are picked clean too.

### 4. Before committing a finalist

For a name that passes availability + recon, also:
- Run **`trademark-basic-search`** (USPTO Class 9/42 + variants) for the legal-risk side.
- Check **social handles, npm `@scope`, GitHub org** — and note the market: a US-only check leaves CN (CNIPA) unverified, which matters if China is a real market.

## Honesty rules

- "Registered" ≠ "for sale" and ≠ "unavailable to you" — some taken domains are parked and purchasable; recon tells you which.
- "Available right now" ≠ "cleared" — availability is necessary, not sufficient; trademark and handle checks still apply.
- A `?` result is a network timeout, not an answer — rerun before concluding.

## Gotchas

- **`.io` (and ccTLDs) silently read FREE under RDAP** — `rdap.org` 404s every `.io` because the registry isn't in the bootstrap. Never trust a bare RDAP 404 for a ccTLD; the script already falls back to whois, but if you hand-roll a check, do the same.
- **macOS `whois name.dev`** only returns the IANA TLD record, so whois can't judge `.dev` — trust RDAP there.
- **zsh word-splitting**: `for n in $names` does NOT split an unquoted variable in zsh (macOS default) — it runs once with the whole string. Use an array `names=(a b c)` or `${=names}`. The bundled Python scripts sidestep this entirely.
- **Network**: these scripts need outbound HTTPS (RDAP) and port-43 (whois). In a sandboxed agent, run them with the sandbox disabled / network allowed.
