#!/bin/sh
# Starts a static file server rooted at openspec/, regardless of the caller's cwd —
# review.html's root-relative asset paths (/tools/engine.js etc.) depend on the server
# root being exactly openspec/, so this always cd's to its own directory first.
cd "$(dirname "$0")" || exit 1
exec python3 -m http.server "$@"
