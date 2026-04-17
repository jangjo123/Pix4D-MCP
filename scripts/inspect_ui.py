from pix4dmatic_mcp.controller import Pix4DMaticController


if __name__ == "__main__":
    controller = Pix4DMaticController()
    print(controller.get_status())
    try:
        window = controller._main_window()
        window.print_control_identifiers(depth=3)
    except Exception as exc:
        print(f"UI inspection failed: {exc}")
