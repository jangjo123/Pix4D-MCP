# Troubleshooting

## No Window Found

Make sure PIX4Dmatic is running in an unlocked Windows desktop session.

## `pywinauto` Import Error

Install the project in editable mode:

```powershell
python -m pip install -e .
```

## Screenshot Fails

Screenshots require an interactive desktop session. Locked remote desktop sessions may fail or capture a blank screen.

## Logs Not Found

Pass `project_dir` to log tools so the server also searches project-local `log`, `logs`, `report`, and `reports` folders.

## Processing Button Not Found

Run `pix4d_get_ui_tree` and look for the current button or menu text. Then pass the discovered labels to `pix4d_start_processing(selectors=[...])`.

PIX4Dmatic may expose Korean UI labels such as `프로세스(P)` and `처리 시작`, depending on the installed language.

## Job Refuses To Run

Jobs must provide an existing `project_path`, or explicitly set `use_current_session` to `true`. This prevents an MCP client from accidentally starting processing in whatever project happens to be open.
