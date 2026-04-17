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
