from pathlib import Path
from typing import Literal


START = "<!-- project-init:windows-shell:start -->"
END = "<!-- project-init:windows-shell:end -->"

Status = Literal["created", "inserted", "updated", "unchanged"]


def replace_managed_block(path: Path, body: str, *, title: str = "# AGENTS") -> Status:
    """Create or replace the repository-managed Windows shell instruction block."""
    if path.exists():
        with path.open(encoding="utf-8", newline="") as source:
            existing = source.read()
    else:
        existing = ""
    start_count = existing.count(START)
    end_count = existing.count(END)
    markers_misordered = start_count == end_count == 1 and existing.index(START) > existing.index(END)
    if start_count != end_count or start_count > 1 or markers_misordered:
        raise ValueError(f"unbalanced managed markers in {path}")

    block = f"{START}\n{body.rstrip()}\n{END}"
    if START in existing:
        prefix, tail = existing.split(START, 1)
        _, suffix = tail.split(END, 1)
        updated = f"{prefix}{block}{suffix}"
        status: Status = "unchanged" if updated == existing else "updated"
    else:
        updated = f"{existing}\n\n{block}\n" if existing else f"{title}\n\n{block}\n"
        status = "inserted" if existing else "created"

    if updated != existing:
        with path.open("w", encoding="utf-8", newline="") as destination:
            destination.write(updated)
    return status


def apply_repo(root: Path, assets_dir: Path) -> dict[str, Status]:
    """Apply agent-specific Windows shell instructions to a repository root."""
    agents_body = (assets_dir / "agents-windows-shell.md").read_text(encoding="utf-8")
    claude_body = (assets_dir / "claude-windows-shell.md").read_text(encoding="utf-8")
    return {
        "AGENTS.md": replace_managed_block(root / "AGENTS.md", agents_body),
        "CLAUDE.md": replace_managed_block(root / "CLAUDE.md", claude_body, title="# CLAUDE"),
    }
