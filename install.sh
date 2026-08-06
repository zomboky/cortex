#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/zomboky/cortex.git"

if command -v uv >/dev/null 2>&1; then
    echo "Installing cortex with uv..."
    uv tool install "git+${REPO_URL}"
elif command -v pipx >/dev/null 2>&1; then
    echo "Installing cortex with pipx..."
    pipx install "git+${REPO_URL}"
else
    echo "Installing cortex with pip..."
    pip install --user "git+${REPO_URL}"
fi

echo "Done. Run 'cortex --version' to verify, then 'cortex config init' to create a starter config."
