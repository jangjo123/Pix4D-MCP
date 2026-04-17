# PIX4Dmatic MCP

Local MCP server for controlling PIX4Dmatic on Windows through GUI automation.

This first version implements the MVP observation and control layer:

- connect to an already running PIX4Dmatic process
- launch PIX4Dmatic when needed
- focus the PIX4Dmatic window
- capture a screenshot
- send hotkeys or plain text
- open an existing project file
- read recent PIX4Dmatic logs
- check expected output files
- collect diagnostics

## Install

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Optional editable package install:

```powershell
python -m pip install -e . --no-build-isolation
```

If package installation is blocked by local permissions, run directly from this checkout:

```powershell
$env:PYTHONPATH = "src"
python -m pix4dmatic_mcp.server
```

## Run

```powershell
$env:PYTHONPATH = "src"
python -m pix4dmatic_mcp.server
```

For Codex or another MCP client, use `examples/mcp_config.example.json` as a starting point.

## Quick Local Checks

PIX4Dmatic is expected to be running in a normal Windows desktop session.

```powershell
python scripts/test_status.py
python scripts/inspect_ui.py
```

## Safety

The server only launches PIX4Dmatic and does not expose a generic process runner. It does not automate login or license changes.
