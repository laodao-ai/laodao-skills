# Task 3 report — explicit user-config merging

## Status

Completed and committed. The implementation preserves unrelated Codex TOML and
Claude JSON settings, performs conservative validation, and writes changes via
an atomic UTF-8/LF sibling replacement with a `.bak` copy of existing files.

## TDD evidence

### RED

1. `python -m pytest project-init/tests/test_windows_shell.py -k 'merge_codex or merge_claude or atomic_write' -v`
   exited 1 during collection, with the expected `ImportError: cannot import
   name 'atomic_write_with_backup' from 'windows_shell'` (the new public
   interfaces did not yet exist).
2. `python -m pytest project-init/tests/test_windows_shell.py -k 'reports_created_when_only_stale_backup_exists' -v`
   exited 1: both Codex and Claude merge functions returned `updated` rather
   than the expected `created` when only a stale `.bak` existed.
3. `python -m pytest project-init/tests/test_windows_shell.py -k 'rejects_inline_parent_structure' -v`
   exited 1: the Codex merge did not raise for an inline
   `shell_environment_policy` parent that cannot safely gain a child table.

### GREEN

1. `python -m pytest project-init/tests/test_windows_shell.py -k 'merge_codex or merge_claude or atomic_write' -v`
   passed: **8 passed, 15 deselected**.
2. `python -m pytest project-init/tests/test_windows_shell.py -v`
   passed: **23 passed in 0.08s**.
3. `git diff --check` exited 0 with no output.

## Files changed

- `project-init/scripts/windows_shell.py`
- `project-init/tests/test_windows_shell.py`

## Commit

`2fc734e feat(project-init): configure agent Python UTF-8 environments`

## Self-review

- Codex content is parsed by `tomllib` before it is modified; duplicate target
  tables and unsafe non-table/inline target structures raise `ValueError`.
- The Codex merge only touches the two required target keys, placing missing
  values before the next table header.
- Claude settings require a JSON object and object-valued `env`; unrelated
  keys remain intact and an existing Git Bash setting is retained only when it
  names a real file.
- Backup creation copies original bytes before `os.replace`; temporary writes
  use UTF-8 and LF newlines.
- Tests use actual temporary files rather than mocks and cover preservation,
  invalid Bash replacement, duplicate/inline TOML rejection, stale backups,
  and byte-preserving backups.

## Concerns

- Deliberately conservative: a semantically equivalent but quoted/otherwise
  non-bare spelling of the Codex target table is rejected instead of being
  rewritten. This avoids guessing at a line-oriented TOML transformation.
- Pre-existing untracked `__pycache__` directories were left untouched and
  excluded from the commit.

## Fix round 1

### Status

Completed all Important review findings plus the LF-contract finding.

### RED evidence

1. `python -m pytest project-init/tests/test_windows_shell.py -k 'quoted_keys or multiline_target or table_text_inside or duplicate_keys_at_any_level or existing_blank_file or preserves_existing_mode or normalizes_all_newlines' -v`
   exited 1 with **8 failed, 2 passed, 23 deselected**. Failures proved that
   quoted TOML keys were rejected, multiline target values were only partly
   replaced, table-looking multiline content was mistaken for a real table,
   duplicate JSON keys were accepted, an empty existing JSON file was accepted,
   and carriage returns were retained.
2. `python -m pytest project-init/tests/test_windows_shell.py -k 'preserves_existing_mode' -v`
   exited 1 with **1 failed, 32 deselected**; replacing a real read-only temp
   file raised `PermissionError` instead of preserving its mode.

### GREEN evidence

1. `python -m pytest project-init/tests/test_windows_shell.py -k 'quoted_keys or multiline_target or table_text_inside or duplicate_keys_at_any_level or existing_blank_file or preserves_existing_mode or normalizes_all_newlines' -v`
   passed with **10 passed, 23 deselected in 0.05s**.
2. `python -m pytest project-init/tests/test_windows_shell.py -v`
   passed with **33 passed in 0.10s**.
3. `git diff --check` exited 0 with no output.

### Files changed

- `project-init/scripts/windows_shell.py`
- `project-init/tests/test_windows_shell.py`
- `.superpowers/sdd/2026-07-29-project-init-windows-git-bash/task-3-report.md`

### Self-review

- TOML source locations are now identified with a multiline-string-aware lexer
  and `tomllib` semantic probes, so quoted spellings map to the same target and
  string content cannot masquerade as a table or assignment.
- Target assignments are parsed through their complete TOML value before the
  entire source span is replaced. An unlocatable/unsafe representation raises
  `ValueError` without writing.
- JSON uses `object_pairs_hook` recursively to reject duplicate keys at every
  object level, and any existing blank file is rejected as invalid JSON.
- Atomic writes normalize CRLF and CR to LF, apply the old mode to the sibling
  temp file before replacement, and restore a temporarily relaxed read-only
  target mode if replacement fails.

### Concerns

- The TOML source locator is intentionally conservative and supports syntax
  needed to safely identify standard/quoted table headers and complete target
  assignments. Valid but unlocatable exotic representations fail closed.
- Pre-existing untracked `__pycache__` directories remain untouched and are not
  part of this fix.
