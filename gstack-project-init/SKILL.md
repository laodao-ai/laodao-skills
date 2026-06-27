---
name: gstack-project-init
description: >
  Use when a repo needs project-level gstack documentation conventions:
  important design, review, and strategy documents should be mirrored under
  docs/gstack/, written in Chinese, indexed for future checkout users, and
  recorded in repo agent instructions such as AGENTS.md.
---

# gstack-project-init

## Purpose

Initialize repo-level gstack documentation rules without changing gstack core.
This skill is for project conventions: decision context should follow the repo,
not remain only in local gstack artifacts or chat history.

## Installed Convention

- Important gstack-generated or gstack-maintained design, review, and strategy docs must be mirrored under `docs/gstack/`.
- Mirrored docs must be written in Chinese, while preserving useful English product terms.
- `docs/gstack/README.md` is the entry point for the directory and should list current mirrored docs.
- Repo agent instructions, usually `AGENTS.md`, must include this as a mandatory project rule.

## Workflow

1. Find the repo root and inspect existing agent instructions (`AGENTS.md`, `CLAUDE.md`, `.codex/`, or local equivalents).
2. Inspect `docs/gstack/` if it exists; otherwise create it.
3. Add or refresh `docs/gstack/README.md` with the mirror rule and index.
4. Add the mandatory gstack documentation rule to `AGENTS.md` or the repo's active agent instruction file.
5. Mirror current authoritative gstack docs into `docs/gstack/` in Chinese.
6. Rewrite stale English mirrored docs into Chinese when the repo language is Chinese.
7. Verify Markdown headings, links, and file names.

## Guardrails

- Do not modify gstack core for a single repo bootstrap problem.
- Do not force unrelated product docs into one shared model just because they live under `docs/gstack/`.
- Do not leave important decisions only in `~/.gstack/`, local chat history, or temporary drafts.
- Preserve unrelated worktree changes; these repositories often have staged or untracked agent artifacts.

## Completion Report

Report the files changed, the mirror directory path, whether any docs were translated, and any unrelated dirty worktree entries that were intentionally left untouched.
