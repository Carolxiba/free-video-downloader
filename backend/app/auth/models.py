from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class AuthCredentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        username = unicodedata.normalize("NFKC", value).strip()
        if not re.fullmatch(r"[\w.\-]+", username, flags=re.UNICODE):
            raise ValueError("用户名只能包含文字、数字、下划线、点或短横线")
        return username


class UserView(BaseModel):
    id: str
    username: str
    created_at: datetime


class AuthMessage(BaseModel):
    message: str
