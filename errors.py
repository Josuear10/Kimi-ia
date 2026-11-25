"""Errors that can be shown to the user. The HTTP layer turns them into JSON responses."""


class AppError(Exception):
    """`message` is safe to show in the UI; technical details go to the server log."""

    status_code = 500
    message = "Ocurrió un error inesperado. Inténtalo de nuevo."

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class AuthRequiredError(AppError):
    status_code = 401
    message = "Tu sesión no es válida o expiró. Inicia sesión de nuevo."


class NotFoundError(AppError):
    status_code = 404
    message = "La conversación no existe."
