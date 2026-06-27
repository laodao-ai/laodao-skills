---
name: trademark-basic-search
description: Run and document a basic trademark search for proposed brand names. Use when the user asks for 基础商标检索, 商标排雷, trademark search, brand name search, naming clearance, or wants to check a proposed brand/product name before domain, logo, launch, repo, or commercial use.
---

# Trademark Basic Search

Use this skill for naming-stage trademark risk screening. Treat the result as a basic search, not legal clearance.

## Core Rules

- Always say this is not legal advice and not lawyer-level trademark clearance.
- Prefer official databases and official search entry points over generic web snippets.
- Distinguish "no obvious exact hit found" from "cleared"; never say a mark is legally safe.
- Search exact names, spacing variants, root-word variants, and adjacent industry terms.
- For current trademark, legal, domain, or company facts, browse or use live sources.

## Workflow

1. Build the query set.
   - Exact: proposed mark, uppercase form, spaced form, common spelling variants.
   - Adjacent: roots, suffixes, obvious abbreviations, competitors, same-word-family marks.
   - Classes: use Class 9 and Class 42 for developer tools/software by default; add product-specific classes when relevant.

2. Run USPTO structured search.
   - Use `scripts/uspto_tmsearch.py` from this skill.
   - Keep the smoke test enabled unless there is a strong reason not to; it verifies the USPTO endpoint with `APPLE`.
   - Example:

```bash
python3 /Users/cheneyzhao/.skills/laodao-skills/trademark-basic-search/scripts/uspto_tmsearch.py \
  PRAGMOKIT "PRAGMO KIT" PRAGMAKIT "PRAGMA KIT" PRAGMO "PRAGMATIC SEMICONDUCTOR" \
  --format markdown
```

3. Check non-US official sources.
   - Read `references/search-sources.md` when you need the current official entry points and limitations.
   - WIPO Global Brand Database may show ALTCHA protection; do not script around it.
   - TMview/EUIPO pages are front-end apps; do not treat failed automated parsing as a clean result.
   - CNIPA/China search may require registration/login; record that manual or attorney review is needed.

4. Run quoted web searches.
   - Search exact quoted terms, e.g. `"PragmoKit"`, `"PRAGMOKIT"`, `"Pragmo Kit"`.
   - Search adjacent terms with product context, e.g. `"Pragmo" software`, `"Pragmatic Semiconductor" trademark`.
   - Record only relevant uses: same/similar mark, same/similar market, same/similar class.

5. Write the report.
   - Include date, mark, target market, target classes, exact queries, adjacent queries, sources, and limitations.
   - Separate confirmed structured results from manual-check requirements.
   - Include a practical conclusion: continue, hold, rename, or escalate to attorney search.

## Report Template

```markdown
## 基础商标检索记录

检索日期：YYYY-MM-DD
拟用名称：<brand>
检索性质：基础排雷，不是法律意见或正式 trademark clearance。

### 检索范围

- 精确名称：...
- 相邻名称：...
- 重点类别：Class 9, Class 42, ...

### USPTO 基础结果

<paste script markdown table>

### WIPO / EUIPO / TMview / CNIPA 状态

- WIPO：...
- EUIPO / TMview：...
- CNIPA：中国区需要人工或代理复核。

### 公开 web 排雷

- Exact match：...
- Adjacent risk：...

### 基础结论

<continue / hold / rename / attorney-review recommendation>

### 参考来源

- <official links>
```

## USPTO Script Notes

The script calls the USPTO TM Search backend:

```text
https://tmsearch.uspto.gov/prod-v1-0-0/tmsearch
```

It sends an Elasticsearch-style POST query using:

- `term` on `WM`
- `match_phrase` on `WM`
- `query_string` against `wordmark` and `wordmarkPseudoText`

If the script fails or the smoke test returns zero results, do not rely on the output. Use the official USPTO web interface manually and state the limitation.

## Final Wording

Use wording like:

- "基础检索未发现明显精确命中。"
- "相邻风险来自 ..."
- "公开发布、logo 投入、商业化或重点市场申请前，需要律师级正式检索。"

Avoid wording like:

- "商标可用。"
- "已经 cleared。"
- "没有风险。"
- "可以放心注册。"
