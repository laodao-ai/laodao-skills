# Task 4 report — CLI, skill workflow, and format integration

## Status

Completed and committed. The three-subcommand CLI now composes the repository,
diagnostic, discovery, and user-configuration functions from Tasks 1–3. It
prints JSON summaries, preserves the read-only diagnostic boundary, and returns
the specified exit codes. The skill workflow and shell LF attribute are also
documented.

## TDD evidence

### RED

1. `python -m pytest project-init/tests/test_windows_shell.py -k 'cli_' -v`
   exited 1 during collection with the expected `ImportError: cannot import
   name 'main' from 'windows_shell'` before the CLI existed.
2. The first minimal implementation run of the same command collected the two
   brief tests; apply passed, while configure failed because an explicitly
   invalid `--bash` incorrectly fell back to the machine's standard Git Bash
   installation (`code` was 0 instead of 2). This exposed the precedence bug
   before GREEN.
3. `python -m pytest project-init/tests/test_windows_shell.py -k
   'cli_diagnose' -v` exited 1 because the missing `diagnose` subcommand printed
   no JSON and argparse returned an invalid-command result.
4. `python -m pytest project-init/tests/test_windows_shell.py -k
   'validates_both_configs' -v` exited 1 because configure updated Codex before
   discovering invalid Claude JSON, leaving a partial user configuration.

### GREEN

1. `python -m pytest project-init/tests/test_windows_shell.py -k 'cli_' -v`
   passed the two brief tests after explicit `--bash` was made authoritative:
   **2 passed, 33 deselected**.
2. The diagnostic cycle passed first in isolation and then with all CLI tests:
   **1 passed, 35 deselected**, followed by **3 passed, 33 deselected**.
3. The cross-config preflight cycle passed first in isolation and then with all
   CLI tests: **1 passed, 36 deselected**, followed by **4 passed, 33
   deselected**.
4. Fresh final verification:

   - `python -m pytest project-init/tests -v`: **37 passed in 0.10s**.
   - `python -m py_compile project-init/scripts/windows_shell.py`: exit 0.
   - `git diff --check`: exit 0 with no output.

## Manual temporary-repository evidence

A fresh repository was initialized under the Windows system temporary
directory. Running `apply-repo` twice produced:

```text
{"AGENTS.md": "created", "CLAUDE.md": "created"}
{"AGENTS.md": "unchanged", "CLAUDE.md": "unchanged"}
AgentsMarkerCount=1
ClaudeMarkerCount=1
```

This verifies real script-relative snippet loading, repeat stability, and one
managed block per target file.

## Files changed

- `project-init/scripts/windows_shell.py`
- `project-init/tests/test_windows_shell.py`
- `project-init/SKILL.md`
- `project-init/assets/.gitattributes`

## Commit

`ab8bda60bfd585c623da10c6ed79f6597044bd89 docs(project-init): integrate Windows Git Bash setup flow`

## Self-review

- `main` resolves `--root` and `--home` without changing process cwd and reads
  snippets from the script's own skill directory.
- `apply-repo` reports per-file statuses as JSON; `diagnose` emits structured
  checks and maps failed checks to exit 1 without writing; invalid invocation,
  missing Git Bash, unsafe config structure, and I/O errors map to exit 2 with
  concise stderr.
- An explicit `--bash` is validated on its own and cannot silently fall back to
  a different machine executable. Without it, the established environment,
  standard candidates, and PATH discovery order remains intact.
- `configure-user` preflights both existing configs using temporary copies
  before changing either user file, preserving the fail-closed behavior of the
  reviewed Task 3 merge functions.
- The responsibility table assigns only `opsx-init` to `opsx-project-init` and
  assigns `project-init:windows-shell` to `project-init`. The documented third
  command explicitly requires user authorization.
- `.gitattributes` now has the exact `*.sh text eol=lf` rule.

## Concerns

- Cross-file preflight prevents deterministic parse/structure failures from
  causing partial configuration. A new external I/O failure or concurrent file
  change between preflight and the two atomic writes could still update only
  one file; guaranteeing a transaction across two independent files is outside
  the existing interfaces.
- The successful manual repository remains at
  `C:\Users\ASUS\AppData\Local\Temp\project-init-task4-dcb8f2ca0d4e4bf7a3719638cd23db53`
  because the execution policy rejected the attempted recursive cleanup before
  it ran.
- Pre-existing untracked `__pycache__` directories remain untouched and are
  excluded from both commits.
