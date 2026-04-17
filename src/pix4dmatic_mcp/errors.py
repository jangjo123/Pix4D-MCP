class Pix4DMaticError(RuntimeError):
    """Base error for PIX4Dmatic automation failures."""

    code = "PIX4DMATIC_ERROR"

    def to_result(self) -> dict:
        return {"ok": False, "code": self.code, "message": str(self)}


class Pix4DNotFoundError(Pix4DMaticError):
    code = "PIX4DMATIC_NOT_FOUND"


class Pix4DWindowNotFoundError(Pix4DMaticError):
    code = "PIX4DMATIC_WINDOW_NOT_FOUND"


class Pix4DTimeoutError(Pix4DMaticError):
    code = "PIX4DMATIC_TIMEOUT"


class Pix4DAutomationError(Pix4DMaticError):
    code = "PIX4DMATIC_AUTOMATION_ERROR"
