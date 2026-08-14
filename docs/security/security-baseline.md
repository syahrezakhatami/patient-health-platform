# Security baseline (Wave 0)

## Implemented

- Environment-based secrets; `.env` is gitignored
- OIDC/JWT validation interface (issuer, audience, expiry, subject, algorithm denylist)
- HS256 only in `local` / `test` / `development`
- Deny-by-default PDP skeleton — no `if role == doctor`
- Security headers
- Configurable CORS allow-list
- Request size limit
- Rate-limit foundation (Redis, in-memory fallback)
- Structured error bodies without stack traces or SQL
- Insert-only audit table + mutation trigger
- Least-privilege DB roles documented and created in local Docker
- OpenAPI disabled in production unless explicitly enabled with debug
- `pip-audit` in CI

## Residual risks

- No identity provider is selected yet; local HS256 is not a production authenticator
- Rate limiting fails open if Redis is unavailable
- Database superuser can still mutate audit rows; WORM/SIEM copy is later
- Object storage in Wave 0 is an abstraction; clinical upload controls are later
- Dependency scan threshold is `pip-audit --strict` and may need allowlisting
- Insider threats, MFA phishing, and prompt injection are out of Wave 0 scope

This baseline does not make the platform “secure.” It makes later waves able to enforce security.

## Future security tests (later waves)

- IDOR / horizontal access
- Tenant isolation
- Patient enumeration
- Consent bypass
- Break-glass abuse
- AI authorization bypass
