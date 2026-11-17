from __future__ import annotations


class AuthError(RuntimeError):
    """可安全展示给用户的认证错误。"""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
