$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$env:UV_CACHE_DIR = Join-Path $root ".uv-cache"

uv run ruff check .
uv run pytest -q
npm --prefix frontend run lint
npm --prefix frontend run build
docker compose config --quiet
