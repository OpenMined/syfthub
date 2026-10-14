"""The error body both servers send: FastAPI's ``detail``, parsed once for every caller."""

from __future__ import annotations

import httpx
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """A FastAPI error body, parsed once. The Hub sends ``detail`` as a string, or as
    ``{"code", "message"}`` on the wallet routes; a 422 sends a list. ``code`` is the
    machine-readable part when there is one; ``message`` is always set."""

    code: str | None = None
    message: str = ""

    @classmethod
    def of(cls, response: httpx.Response) -> ErrorDetail:
        try:
            body = response.json()
        except ValueError:
            return cls(message=response.text[:200])
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, str):
            return cls(message=detail)
        if isinstance(detail, dict):
            code = detail.get("code")
            message = detail.get("message")
            return cls(
                code=str(code) if code else None,
                message=str(message) if message else str(detail)[:200],
            )
        if detail is not None:
            return cls(message=str(detail)[:200])
        return cls(message=response.text[:200])

    def __str__(self) -> str:
        return f"{self.code}: {self.message}" if self.code else self.message


def detail_of(response: httpx.Response) -> str:
    """The error as one line: ``CODE: message`` when the body carries a code."""
    return str(ErrorDetail.of(response))
