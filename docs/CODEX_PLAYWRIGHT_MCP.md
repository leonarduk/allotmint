# Codex Playwright MCP setup

This guide provides exact, copy/paste-ready registration steps for enabling a Playwright MCP server with Codex.

## 1) Prerequisite

Install Node.js (18+) so `npx` is available.

## 2) Codex + MCP registration (exact steps)

### Option A (recommended): Codex CLI config file

1. Create the Codex config directory and file:

```bash
mkdir -p ~/.codex
cat > ~/.codex/config.toml <<'TOML'
[mcp_servers.playwright]
command = "npx"
args = ["-y", "@playwright/mcp@latest"]
TOML
```

2. Save the file at this exact location:
   - macOS/Linux: `~/.codex/config.toml`
   - Windows (PowerShell): `$HOME/.codex/config.toml`

This location is where Codex CLI reads MCP server registrations.

### Option B: Codex app MCP settings UI

If you are using the Codex app UI instead of the CLI config file:

1. Open **Settings**.
2. Open **MCP Settings** (or **Tools → MCP Servers**, depending on app version).
3. Add a custom server with:
   - Name: `playwright`
   - Command: `npx`
   - Args: `-y @playwright/mcp@latest`
4. Save and restart the Codex session for the workspace.

## 3) Verify registration

Run this command and confirm `playwright` appears in the output:

```bash
codex mcp list
```

If `playwright` is not listed, re-check the config path and restart Codex.

## 4) Workspace note

If your environment uses per-workspace MCP policies, ensure the `playwright` server is enabled for this repository after registration.
