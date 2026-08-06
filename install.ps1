$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/zomboky/cortex.git"

if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "Installing cortex with uv..."
    uv tool install "git+$RepoUrl"
} elseif (Get-Command pipx -ErrorAction SilentlyContinue) {
    Write-Host "Installing cortex with pipx..."
    pipx install "git+$RepoUrl"
} else {
    Write-Host "Installing cortex with pip..."
    pip install --user "git+$RepoUrl"
}

Write-Host "Done. Run 'cortex --version' to verify, then 'cortex config init' to create a starter config."
