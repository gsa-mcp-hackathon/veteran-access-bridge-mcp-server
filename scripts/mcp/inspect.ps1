param()

$ErrorActionPreference = "Stop"

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw "npx was not found. Install Node.js/npm before running MCP Inspector."
}

Write-Host "Starting MCP Inspector for Veteran Access MCP over stdio..."
& npx @modelcontextprotocol/inspector uv run veteran-access-mcp
