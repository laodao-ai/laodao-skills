# project-init Windows Git Bash 双代理支持 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `project-init` 为 Codex 与 Claude Code 安装各自正确的 Windows Git Bash 仓库指令，并可诊断及显式配置两端的 Python UTF-8 用户环境。

**Architecture:** 新增一个无第三方依赖的 `windows_shell.py`，把托管块更新、Git Bash 发现、配置合并和诊断拆成可独立测试的函数，再用三个 CLI 子命令组合。两个 Markdown snippet 分别承载 Codex 与 Claude Code 的宿主适配规则，`SKILL.md` 负责调用策略与安全边界。

**Tech Stack:** Python 3.11+ 标准库（`argparse`、`json`、`pathlib`、`subprocess`、`tempfile`、`tomllib`）、pytest、Markdown、TOML、JSON。

## Global Constraints

- 仓库命令、`.sh`、路径、变量、管道和重定向采用 Bash/POSIX 语义。
- Codex 的 PowerShell 宿主显式调用 Git Bash；Claude Code 直接使用 Bash 工具。
- 不修改 `opsx-init` 托管块或用户手写内容。
- `configure-user` 是唯一允许修改用户主目录的动作，且必须由用户明确授权。
- 不向仓库提交机器相关的 Git Bash 路径。
- 不自动编辑 `~/.bashrc`。
- 配置结构不安全、标记残缺或 Git Bash 缺失时停止并给出明确错误。
- 所有新增文本文件使用 UTF-8、LF；不新增 shell 脚本。
- 不修改 OpenSpec workflow bundle 或 `minimize-repo-footprint` change。

## File Map

- `project-init/assets/snippets/agents-windows-shell.md`：Codex 专用仓库指令正文。
- `project-init/assets/snippets/claude-windows-shell.md`：Claude Code 专用仓库指令正文。
- `project-init/scripts/windows_shell.py`：托管块、配置合并、发现、诊断和 CLI。
- `project-init/tests/test_windows_shell.py`：对临时目录与受控 subprocess 的行为测试。
- `project-init/SKILL.md`：执行流程、职责边界、命令和完成报告。
- `project-init/assets/.gitattributes`：显式声明 `.sh` 为 LF。

---

### Task 1: 仓库级双适配器托管块

**Files:**
- Create: `project-init/assets/snippets/agents-windows-shell.md`
- Create: `project-init/assets/snippets/claude-windows-shell.md`
- Create: `project-init/scripts/windows_shell.py`
- Create: `project-init/tests/test_windows_shell.py`

**Interfaces:**
- Produces: `replace_managed_block(path: Path, body: str) -> Literal["created", "inserted", "updated", "unchanged"]`
- Produces: `apply_repo(root: Path, assets_dir: Path) -> dict[str, str]`
- Managed markers: `<!-- project-init:windows-shell:start -->` and `<!-- project-init:windows-shell:end -->`

- [ ] **Step 1: Write failing tests for creation, preservation, idempotence, and malformed markers**

```python
def test_apply_repo_creates_agent_specific_files(tmp_path, assets_dir):
    result = apply_repo(tmp_path, assets_dir)
    agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    claude = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "PowerShell" in agents and "bash.exe" in agents
    assert "Claude Code's Bash tool" in claude
    assert "& 'C:\\Program Files" not in claude
    assert result == {"AGENTS.md": "created", "CLAUDE.md": "created"}

def test_apply_repo_preserves_user_and_opsx_content_and_is_idempotent(tmp_path, assets_dir):
    original = "# AGENTS\n\nuser text\n\n<!-- opsx-init:start -->\nopsx\n<!-- opsx-init:end -->\n"
    (tmp_path / "AGENTS.md").write_text(original, encoding="utf-8")
    apply_repo(tmp_path, assets_dir)
    once = (tmp_path / "AGENTS.md").read_bytes()
    apply_repo(tmp_path, assets_dir)
    twice = (tmp_path / "AGENTS.md").read_bytes()
    assert original.rstrip() in once.decode("utf-8")
    assert once == twice

def test_replace_managed_block_rejects_unbalanced_markers(tmp_path):
    path = tmp_path / "AGENTS.md"
    path.write_text("before\n<!-- project-init:windows-shell:start -->\nbroken\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unbalanced managed markers"):
        replace_managed_block(path, "body")
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python -m pytest project-init/tests/test_windows_shell.py -k 'apply_repo or replace_managed_block' -v
```

Expected: collection/import fails because `project-init/scripts/windows_shell.py` and its functions do not exist.

- [ ] **Step 3: Implement snippets and minimal managed-block functions**

Implement constants and behavior:

```python
START = "<!-- project-init:windows-shell:start -->"
END = "<!-- project-init:windows-shell:end -->"

def replace_managed_block(path: Path, body: str) -> str:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing.count(START) != existing.count(END) or existing.count(START) > 1:
        raise ValueError(f"unbalanced managed markers in {path}")
    block = f"{START}\n{body.rstrip()}\n{END}"
    if START in existing:
        prefix, tail = existing.split(START, 1)
        _, suffix = tail.split(END, 1)
        updated = f"{prefix}{block}{suffix}"
        status = "unchanged" if updated == existing else "updated"
    else:
        updated = f"{existing.rstrip()}\n\n{block}\n" if existing else f"# AGENTS\n\n{block}\n"
        status = "inserted" if existing else "created"
    if updated != existing:
        path.write_text(updated, encoding="utf-8", newline="\n")
    return status
```

`apply_repo` reads the two exact snippet files and applies them to `AGENTS.md` and `CLAUDE.md`; when creating `CLAUDE.md`, its title must be `# CLAUDE` rather than `# AGENTS`（通过 `replace_managed_block` 的可选 `title` 参数实现）。

- [ ] **Step 4: Run focused tests and verify GREEN**

```bash
python -m pytest project-init/tests/test_windows_shell.py -k 'apply_repo or replace_managed_block' -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 1**

```bash
git add project-init/assets/snippets project-init/scripts/windows_shell.py project-init/tests/test_windows_shell.py
git commit -m "feat(project-init): add Git Bash agent instruction blocks"
```

### Task 2: Git Bash 发现与只读诊断

**Files:**
- Modify: `project-init/scripts/windows_shell.py`
- Modify: `project-init/tests/test_windows_shell.py`

**Interfaces:**
- Consumes: managed-block functions from Task 1.
- Produces: `discover_git_bash(env: Mapping[str, str], candidates: Sequence[Path], which: Callable[[str], str | None]) -> Path | None`
- Produces: `probe_python_utf8(bash: Path, runner: Callable[..., CompletedProcess[str]] = subprocess.run) -> dict[str, object]`
- Produces: `diagnose(home: Path, env: Mapping[str, str]) -> tuple[list[dict[str, object]], bool]`

- [ ] **Step 1: Write failing discovery and probe tests**

```python
def test_discover_git_bash_prefers_valid_claude_setting(tmp_path):
    configured = tmp_path / "configured" / "bash.exe"
    standard = tmp_path / "standard" / "bash.exe"
    configured.parent.mkdir(); configured.touch()
    standard.parent.mkdir(); standard.touch()
    found = discover_git_bash(
        {"CLAUDE_CODE_GIT_BASH_PATH": str(configured)},
        [standard],
        lambda _: None,
    )
    assert found == configured

def test_discover_git_bash_ignores_wsl_launcher(tmp_path):
    assert discover_git_bash({}, [], lambda _: r"C:\\Windows\\System32\\bash.exe") is None

def test_probe_python_utf8_parses_machine_readable_output(tmp_path):
    bash = tmp_path / "bash.exe"; bash.touch()
    completed = subprocess.CompletedProcess([], 0, '{"utf8_mode": 1, "stdout": "utf-8"}\n', "")
    result = probe_python_utf8(bash, runner=lambda *a, **k: completed)
    assert result["ok"] is True
```

- [ ] **Step 2: Run focused tests and verify RED**

```bash
python -m pytest project-init/tests/test_windows_shell.py -k 'discover_git_bash or probe_python_utf8' -v
```

Expected: imports fail for missing discovery/probe functions.

- [ ] **Step 3: Implement deterministic discovery and UTF-8 probe**

The probe must execute one argument-safe command through `bash.exe -lc`:

```python
probe = (
    "python -c 'import json,sys; "
    "print(json.dumps({\"utf8_mode\":sys.flags.utf8_mode,"
    "\"stdout\":sys.stdout.encoding}))'"
)
completed = runner([str(bash), "-lc", probe], text=True, encoding="utf-8", capture_output=True)
```

Return structured checks without printing the full inherited environment. `diagnose` also inspects the two user config files and warns if Claude has `CLAUDE_CODE_USE_POWERSHELL_TOOL=1`.

- [ ] **Step 4: Run focused tests and verify GREEN**

```bash
python -m pytest project-init/tests/test_windows_shell.py -k 'discover_git_bash or probe_python_utf8 or diagnose' -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add project-init/scripts/windows_shell.py project-init/tests/test_windows_shell.py
git commit -m "feat(project-init): diagnose Windows Git Bash runtime"
```

### Task 3: 显式合并 Codex 与 Claude Code 用户配置

**Files:**
- Modify: `project-init/scripts/windows_shell.py`
- Modify: `project-init/tests/test_windows_shell.py`

**Interfaces:**
- Consumes: `discover_git_bash` from Task 2.
- Produces: `merge_codex_config(path: Path) -> Literal["created", "updated", "unchanged"]`
- Produces: `merge_claude_settings(path: Path, bash: Path) -> Literal["created", "updated", "unchanged"]`
- Produces: `atomic_write_with_backup(path: Path, content: str) -> Path | None`

- [ ] **Step 1: Write failing tests for safe TOML/JSON merging**

```python
def test_merge_codex_config_preserves_other_keys(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('model = "gpt"\n\n[shell_environment_policy.set]\nKEEP = "yes"\n', encoding="utf-8")
    merge_codex_config(path)
    text = path.read_text(encoding="utf-8")
    assert 'model = "gpt"' in text
    assert 'KEEP = "yes"' in text
    assert 'PYTHONUTF8 = "1"' in text
    assert 'PYTHONIOENCODING = "utf-8"' in text

def test_merge_codex_config_rejects_duplicate_target_table(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[shell_environment_policy.set]\nA='1'\n[shell_environment_policy.set]\nB='2'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        merge_codex_config(path)

def test_merge_claude_settings_preserves_existing_fields_and_valid_bash(tmp_path):
    existing = tmp_path / "existing-bash.exe"; existing.touch()
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"permissions": {"allow": ["Read"]}, "env": {"CLAUDE_CODE_GIT_BASH_PATH": str(existing), "KEEP": "yes"}}), encoding="utf-8")
    merge_claude_settings(path, tmp_path / "other-bash.exe")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["permissions"] == {"allow": ["Read"]}
    assert data["env"]["CLAUDE_CODE_GIT_BASH_PATH"] == str(existing)
    assert data["env"]["PYTHONUTF8"] == "1"
```

- [ ] **Step 2: Run focused tests and verify RED**

```bash
python -m pytest project-init/tests/test_windows_shell.py -k 'merge_codex or merge_claude or atomic_write' -v
```

Expected: imports fail for missing merge functions.

- [ ] **Step 3: Implement conservative merges and backup writes**

For Codex, use `tomllib.loads` for validation, then perform a line-oriented update only when the target table occurs zero or one time. Insert or replace only `PYTHONUTF8` and `PYTHONIOENCODING` before the next table header. Reject duplicate target tables and non-table target structures.

For Claude, parse a JSON object, require `env` to be an object, merge the three string values, and preserve an existing Git Bash path only when `Path(value).is_file()`.

`atomic_write_with_backup` creates `<name>.bak` before changing an existing file, writes a UTF-8/LF temp sibling, then calls `os.replace`.

- [ ] **Step 4: Run focused and full tests and verify GREEN**

```bash
python -m pytest project-init/tests/test_windows_shell.py -v
```

Expected: all tests pass with no warnings.

- [ ] **Step 5: Commit Task 3**

```bash
git add project-init/scripts/windows_shell.py project-init/tests/test_windows_shell.py
git commit -m "feat(project-init): configure agent Python UTF-8 environments"
```

### Task 4: CLI、skill 文档与格式约束集成

**Files:**
- Modify: `project-init/scripts/windows_shell.py`
- Modify: `project-init/tests/test_windows_shell.py`
- Modify: `project-init/SKILL.md`
- Modify: `project-init/assets/.gitattributes`

**Interfaces:**
- Consumes: all functions from Tasks 1–3.
- Produces CLI: `python project-init/scripts/windows_shell.py {apply-repo|diagnose|configure-user} --root PATH [--home PATH]`

- [ ] **Step 1: Write failing CLI tests**

```python
def test_cli_apply_repo_prints_json_summary(tmp_path, capsys):
    code = main(["apply-repo", "--root", str(tmp_path)])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["AGENTS.md"] == "created"

def test_cli_configure_user_requires_existing_git_bash(tmp_path, capsys):
    code = main(["configure-user", "--home", str(tmp_path), "--bash", str(tmp_path / "missing.exe")])
    assert code == 2
    assert "Git Bash" in capsys.readouterr().err
```

- [ ] **Step 2: Run CLI tests and verify RED**

```bash
python -m pytest project-init/tests/test_windows_shell.py -k 'cli_' -v
```

Expected: import or assertion failure because `main`/subcommands do not exist.

- [ ] **Step 3: Implement argparse CLI and JSON summaries**

`main(argv: Sequence[str] | None = None) -> int` must:

- resolve the repository root without changing process cwd;
- use script-relative `assets/snippets` paths;
- keep `diagnose` read-only;
- require a valid discovered or `--bash` path for `configure-user`;
- print machine-readable JSON to stdout and concise errors to stderr;
- return `0` success, `1` failed diagnosis, `2` invalid invocation/configuration.

- [ ] **Step 4: Update SKILL.md and `.gitattributes`**

Document exact commands:

```bash
python <skill-dir>/scripts/windows_shell.py apply-repo --root .
python <skill-dir>/scripts/windows_shell.py diagnose --root .
python <skill-dir>/scripts/windows_shell.py configure-user --root .
```

State that the third command requires explicit user authorization. Revise the responsibility table so `opsx-project-init` owns only `opsx-init`, while `project-init` owns `project-init:windows-shell`. Add this explicit attribute:

```gitattributes
*.sh text eol=lf
```

- [ ] **Step 5: Run all project-init tests and syntax checks**

```bash
python -m pytest project-init/tests -v
python -m py_compile project-init/scripts/windows_shell.py
git diff --check
```

Expected: all tests pass, compilation exits 0, and `git diff --check` emits no errors.

- [ ] **Step 6: Exercise the CLI against a temporary repository**

```bash
tmpdir="$(mktemp -d)"
git -C "$tmpdir" init
python project-init/scripts/windows_shell.py apply-repo --root "$tmpdir"
python project-init/scripts/windows_shell.py apply-repo --root "$tmpdir"
grep -c '<!-- project-init:windows-shell:start -->' "$tmpdir/AGENTS.md"
grep -c '<!-- project-init:windows-shell:start -->' "$tmpdir/CLAUDE.md"
```

Expected: both apply calls succeed and both counts equal `1`.

- [ ] **Step 7: Commit Task 4**

```bash
git add project-init/SKILL.md project-init/assets/.gitattributes project-init/scripts/windows_shell.py project-init/tests/test_windows_shell.py
git commit -m "docs(project-init): integrate Windows Git Bash setup flow"
```

### Task 5: Final regression and requirements verification

**Files:**
- Verify only; modify earlier files only if a failing requirement exposes a defect, following a new RED/GREEN cycle.

**Interfaces:**
- Consumes the complete CLI and documentation.
- Produces fresh verification evidence.

- [ ] **Step 1: Run the targeted suite**

```bash
python -m pytest project-init/tests -v
```

Expected: zero failures.

- [ ] **Step 2: Run relevant repository regression tests**

```bash
python -m pytest opsx-project-init/tests -q
```

Expected: zero failures, proving the independent managed block did not regress OpenSpec initialization.

- [ ] **Step 3: Verify formatting and inspect the final diff**

```bash
python -m py_compile project-init/scripts/windows_shell.py
git diff --check HEAD~4..HEAD
git status --short
git log -5 --oneline
```

Expected: compilation and diff checks exit 0; status contains no unintended files; log shows the design and task commits.

- [ ] **Step 4: Check every design completion criterion**

Confirm from tests and snippets:

- new and existing OpenSpec repositories are supported;
- Codex contains the PowerShell-host adapter and Claude does not;
- Python UTF-8 variables are configured for both agents;
- repeat application is byte-stable;
- user home changes occur only through `configure-user`;
- no workflow bundle or active OpenSpec change artifact was modified.
