# UI Selectors

Initial selector policy:

- Prefer English PIX4Dmatic UI text.
- Keep Korean text as fallback where known.
- Use UI Automation selectors first.
- Coordinate clicking is intentionally disabled for the first version.

Known main window titles:

- `PIX4Dmatic`
- `Pix4Dmatic`

Observed Korean menu labels:

- `파일(F)`
- `편집(E)`
- `프로세스(P)`

Processing start candidates are kept in `src/pix4dmatic_mcp/selectors.py`. Use `pix4d_get_ui_tree` after PIX4Dmatic updates to refresh selectors.
