## Windows shell execution

- Use Bash/POSIX semantics for repository commands, `.sh` scripts, paths, variables, pipelines, and redirection.
- Use PowerShell only for a Windows-host or bootstrap operation that cannot reasonably run through Git Bash, and state why.
- When a background tool is hosted by PowerShell, invoke Git Bash explicitly with `& 'C:\Program Files\Git\bin\bash.exe' -lc '<command>'`.
- Correctly quote complex commands for both the outer PowerShell shell and the inner Bash shell.
