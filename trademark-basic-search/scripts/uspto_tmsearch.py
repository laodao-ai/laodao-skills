#!/usr/bin/env python3
"""Query the USPTO TM Search backend for basic naming-stage screening."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ENDPOINT = "https://tmsearch.uspto.gov/prod-v1-0-0/tmsearch"
DEFAULT_SOURCE = [
    "id",
    "wordmark",
    "registrationId",
    "internationalClass",
    "goodsAndServices",
    "ownerName",
    "alive",
]


@dataclass
class SearchResult:
    term: str
    query_term: str
    status: int
    total: int | None
    hits: list[dict[str, Any]]
    error: str | None = None


def escape_query_string(term: str) -> str:
    reserved = set(r'+-=&&||><!(){}[]^"~*?:\/')
    out: list[str] = []
    i = 0
    while i < len(term):
        if term.startswith("&&", i) or term.startswith("||", i):
            out.append("\\" + term[i : i + 2])
            i += 2
            continue
        ch = term[i]
        if ch in reserved:
            out.append("\\" + ch)
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def build_payload(term: str, size: int) -> dict[str, Any]:
    return {
        "query": {
            "bool": {
                "must": [
                    {
                        "bool": {
                            "should": [
                                {"term": {"WM": {"value": term, "boost": 6}}},
                                {"match_phrase": {"WM": {"query": term, "boost": 5}}},
                                {
                                    "query_string": {
                                        "query": escape_query_string(term),
                                        "default_operator": "AND",
                                        "fields": ["wordmark", "wordmarkPseudoText"],
                                    }
                                },
                            ]
                        }
                    }
                ]
            }
        },
        "size": size,
        "from": 0,
        "track_total_hits": True,
        "_source": DEFAULT_SOURCE,
    }


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=body,
        headers={
            "content-type": "application/json",
            "origin": "https://tmsearch.uspto.gov",
            "referer": "https://tmsearch.uspto.gov/",
            "user-agent": "Mozilla/5.0",
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        return response.status, json.loads(raw)


def query_term(term: str, size: int, timeout: float, preserve_case: bool) -> SearchResult:
    query = term if preserve_case else term.upper()
    try:
        status, data = post_json(ENDPOINT, build_payload(query, size), timeout)
        hits_obj = data.get("hits") or {}
        hits = hits_obj.get("hits") or []
        return SearchResult(
            term=term,
            query_term=query,
            status=status,
            total=hits_obj.get("totalValue"),
            hits=hits,
        )
    except HTTPError as exc:
        return SearchResult(term, query, exc.code, None, [], f"HTTP {exc.code}: {exc.reason}")
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return SearchResult(term, query, 0, None, [], str(exc))


def summarize_hit(hit: dict[str, Any]) -> str:
    source = hit.get("source") or {}
    wordmark = source.get("wordmark") or "(no wordmark)"
    serial = source.get("id") or "-"
    registration = source.get("registrationId") or "-"
    classes = source.get("internationalClass") or []
    if isinstance(classes, list):
        classes_text = ", ".join(classes)
    else:
        classes_text = str(classes)
    alive = source.get("alive")
    return f"{wordmark} | SN {serial} | RN {registration} | {classes_text} | alive={alive}"


def emit_markdown(results: list[SearchResult], smoke: SearchResult | None) -> None:
    if smoke:
        print("### USPTO Endpoint Smoke Test")
        total = "ERROR" if smoke.total is None else str(smoke.total)
        print()
        print(f"- Term: `{smoke.query_term}`")
        print(f"- Status: `{smoke.status}`")
        print(f"- Total: `{total}`")
        if smoke.error:
            print(f"- Error: `{smoke.error}`")
        print()

    print("### USPTO Basic Results")
    print()
    print("| Query | Status | Total | Top hits |")
    print("|---|---:|---:|---|")
    for result in results:
        total = "ERROR" if result.total is None else str(result.total)
        top = "<br>".join(summarize_hit(hit) for hit in result.hits[:3])
        if not top:
            top = result.error or "-"
        print(f"| `{result.query_term}` | {result.status} | {total} | {top} |")
    print()

    for result in results:
        if not result.hits:
            continue
        print(f"#### `{result.query_term}` hits")
        print()
        for hit in result.hits:
            print(f"- {summarize_hit(hit)}")
        print()


def emit_json(results: list[SearchResult], smoke: SearchResult | None) -> None:
    payload = {
        "endpoint": ENDPOINT,
        "smoke": smoke.__dict__ if smoke else None,
        "results": [result.__dict__ for result in results],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query USPTO TM Search backend for basic trademark screening."
    )
    parser.add_argument("terms", nargs="+", help="Trademark terms to search.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--size", type=int, default=5, help="Hits to return per term.")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--sleep", type=float, default=0.2, help="Delay between requests.")
    parser.add_argument("--smoke-term", default="APPLE")
    parser.add_argument("--no-smoke-test", action="store_true")
    parser.add_argument("--preserve-case", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    smoke = None
    if not args.no_smoke_test:
        smoke = query_term(args.smoke_term, 1, args.timeout, args.preserve_case)
        if args.sleep:
            time.sleep(args.sleep)

    results = []
    for term in args.terms:
        results.append(query_term(term, args.size, args.timeout, args.preserve_case))
        if args.sleep:
            time.sleep(args.sleep)

    if args.format == "json":
        emit_json(results, smoke)
    else:
        emit_markdown(results, smoke)

    if smoke and (smoke.total is None or smoke.total == 0):
        print(
            "WARNING: USPTO smoke test did not return results; do not rely on automated output.",
            file=sys.stderr,
        )
        return 2
    if any(result.total is None for result in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
