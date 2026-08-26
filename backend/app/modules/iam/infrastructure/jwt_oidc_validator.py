from datetime import UTC, datetime
from typing import Any

import jwt
from jwt import PyJWKClient

from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.modules.iam.application.ports import AuthContext


class JwtOidcTokenValidator:
    """OIDC/JWT access-token validator.

    Production path: JWKS from AUTH_JWKS_URL.
    Local/test path: HS256 shared secret, only when APP_ENV allows it.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._jwk_client: PyJWKClient | None = None
        if settings.auth_jwks_url:
            self._jwk_client = PyJWKClient(settings.auth_jwks_url)

    async def validate(self, token: str) -> AuthContext:
        if not token or token.count(".") != 2:
            raise UnauthorizedError("Malformed token")
        try:
            header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError as exc:
            raise UnauthorizedError("Malformed token") from exc

        algorithm = header.get("alg")
        if algorithm in {None, "none", "None"}:
            raise UnauthorizedError("Token algorithm is not allowed")

        try:
            payload = self._decode(token, algorithm)
        except jwt.ExpiredSignatureError as exc:
            raise UnauthorizedError("Token has expired") from exc
        except jwt.InvalidIssuerError as exc:
            raise UnauthorizedError("Token issuer is invalid") from exc
        except jwt.InvalidAudienceError as exc:
            raise UnauthorizedError("Token audience is invalid") from exc
        except jwt.InvalidTokenError as exc:
            raise UnauthorizedError("Token is invalid") from exc

        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise UnauthorizedError("Token subject is missing")

        exp = payload.get("exp")
        if not isinstance(exp, int):
            raise UnauthorizedError("Token expiration is missing")

        audience = payload.get("aud")
        if isinstance(audience, list):
            values = [item for item in audience if isinstance(item, str) and item]
            if len(values) != 1 or len(set(values)) != 1:
                raise UnauthorizedError("Token audience is invalid")
            audience_value = values[0]
        elif isinstance(audience, str) and audience:
            audience_value = audience
        else:
            raise UnauthorizedError("Token audience is invalid")

        issuer = payload.get("iss")
        if not isinstance(issuer, str):
            raise UnauthorizedError("Token issuer is invalid")

        raw_token_use = payload.get("typ") or payload.get("token_use") or "access"
        token_use = raw_token_use if isinstance(raw_token_use, str) else "access"

        safe_claims = {
            key: str(value)
            for key, value in payload.items()
            if key in {"sub", "iss", "aud", "exp", "iat", "scope", "azp"}
            and not isinstance(value, dict)
        }
        return AuthContext(
            subject=subject,
            issuer=issuer,
            audience=audience_value,
            expires_at=datetime.fromtimestamp(exp, tz=UTC),
            token_use=token_use,
            claims=safe_claims,
        )

    def _decode(self, token: str, algorithm: object) -> dict[str, Any]:
        options = {
            "require": ["exp", "iss", "aud", "sub"],
            "verify_exp": True,
            "verify_iss": True,
            "verify_aud": True,
        }
        decode_kwargs: dict[str, Any] = {
            "issuer": self._settings.auth_issuer,
            "audience": [
                self._settings.auth_audience,
                self._settings.auth_platform_audience,
                self._settings.auth_patient_audience,
            ],
            "options": options,
        }
        if self._jwk_client is not None:
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)
            payload: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                **decode_kwargs,
            )
            return payload
        if self._settings.allow_dev_hs256 and self._settings.auth_dev_hs256_secret is not None:
            if algorithm != "HS256":
                raise UnauthorizedError("Token algorithm is not allowed")
            hs_payload: dict[str, Any] = jwt.decode(
                token,
                self._settings.auth_dev_hs256_secret.get_secret_value(),
                algorithms=["HS256"],
                **decode_kwargs,
            )
            return hs_payload
        raise UnauthorizedError("Token validator is not configured")
