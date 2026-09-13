"""Минимальный immutable principal для подтверждённой Clerk-сессии."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class Principal:
    """Идентичность субъекта после проверки session token."""

    subject_id: str
    issuer: str
    token_type: Literal["session_token"] = "session_token"
