#!/bin/bash
# Open this file from its extracted folder, not from inside the ZIP archive.
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
PYTHON_BIN=""
for candidate in python3 python3.14 python3.13 python3.12; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)' >/dev/null 2>&1; then
    PYTHON_BIN="$candidate"
    break
  fi
done
if [ -z "$PYTHON_BIN" ]; then
  echo 'Plan Finder needs the free Python 3.12 or newer.'
  echo 'Install it from https://www.python.org/downloads/macos/ and open this launcher again.'
  read -r -p 'Press Return to close this window. '
  exit 1
fi
"$PYTHON_BIN" run_local.py
RESULT=$?
if [ "$RESULT" -ne 0 ]; then
  read -r -p 'Press Return to close this window. '
fi
exit "$RESULT"
