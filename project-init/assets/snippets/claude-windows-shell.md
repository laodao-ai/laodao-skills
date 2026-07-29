## Windows shell execution

- Use Bash/POSIX semantics for repository commands, `.sh` scripts, paths, variables, pipelines, and redirection.
- Use Claude Code's Bash tool directly; do not generate a PowerShell `& ...` wrapper in that tool.
- If Git Bash is missing or cannot be located, stop repository commands and report diagnostics.
- Do not enable or depend on a preview PowerShell tool for project tasks.
