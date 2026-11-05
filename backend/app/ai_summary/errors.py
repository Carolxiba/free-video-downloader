from __future__ import annotations


class AiSummaryError(RuntimeError):
    """可安全展示给用户的摘要流程错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
