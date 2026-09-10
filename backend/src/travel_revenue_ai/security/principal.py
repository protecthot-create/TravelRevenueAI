"""Минимальный immutable principal для подтверждённой Clerk-сессии."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    """Идентичность субъекта после проверки session token."""

    subject_id: str
    issuer: str
    token_type: str
