from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class AuthContext:
    subject: str
    issuer: str
    audience: str
    expires_at: datetime
    token_use: str
    claims: dict[str, str]


class TokenValidator(Protocol):
    async def validate(self, token: str) -> AuthContext:
        """Validate an access token. Must check signature, issuer, audience, and expiry."""
        ...
