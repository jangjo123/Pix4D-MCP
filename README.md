# PIX4Dmatic MCP

Local MCP server for controlling PIX4Dmatic on Windows through GUI automation.

This first version implements the MVP observation and control layer:

- connect to an already running PIX4Dmatic process
- launch PIX4Dmatic when needed
- focus the PIX4Dmatic window
- capture a screenshot
- send hotkeys or plain text
- click visible UI text or menu-like paths
- inspect the UI Automation tree
- open an existing project file
- start processing from visible processing controls
- wait until PIX4Dmatic becomes idle
- run a guarded JSON job for an existing project or current session
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

## Configuration

The server loads defaults automatically, then optionally reads:

- `PIX4DMATIC_MCP_CONFIG`
- `pix4dmatic_mcp_config.json` in the current working directory
- `config/pix4dmatic_mcp_config.json` in the current working directory

Useful environment overrides:

- `PIX4DMATIC_EXE`
- `PIX4DMATIC_MCP_DIAGNOSTICS_DIR`

See `examples/pix4dmatic_mcp_config.example.json`.

For Codex or another MCP client, use `examples/mcp_config.example.json` as a starting point.

## Quick Local Checks

PIX4Dmatic is expected to be running in a normal Windows desktop session.

```powershell
$env:PYTHONPATH = "src"
python scripts/test_status.py
python scripts/inspect_ui.py
```

## MCP Tools

Session and observation:

- `pix4d_launch`
- `pix4d_focus`
- `pix4d_get_status`
- `pix4d_screenshot`
- `pix4d_get_ui_tree`

Low-level UI control:

- `pix4d_send_hotkey`
- `pix4d_type_text`
- `pix4d_click_text`
- `pix4d_click_menu`

Project and processing:

- `pix4d_open_project`
- `pix4d_start_processing`
- `pix4d_wait_until_idle`
- `pix4d_run_job`
- `pix4d_run_job_object`

Logs and outputs:

- `pix4d_read_latest_logs`
- `pix4d_find_log_errors`
- `pix4d_check_outputs`
- `pix4d_collect_diagnostics`

## Job Safety

`pix4d_run_job_object` and `pix4d_run_job` will start processing. A job must either provide `project_path` or explicitly set `use_current_session` to `true`.

Use `dry_run: true` to validate job intent without clicking the PIX4Dmatic UI.

## Safety

The server only launches PIX4Dmatic and does not expose a generic process runner. It does not automate login or license changes.
