# Identifier policy

## Ownership

An identifier is owned by its `identifier_system` and, when applicable, `organization_id`.

- Hospital A MRN `1001` and Hospital B MRN `1001` are different identifiers.
- The platform UUID is the longitudinal identity.
- Organization MRNs are never overwritten by another organization’s MRN.

## Value representations

| Field | Why it exists |
|---|---|
| `identifier_value` (raw) | Original representation for provenance and audit. Source of truth for what was entered. |
| `normalized_value` | Deterministic, system-specific form used for uniqueness and exact match. |
| `matching_value` | Reserved for future matching keys. In Wave 1 it equals `normalized_value`. |

A transformed value is never stored as the only representation.

## Normalization (Wave 1)

| System / type | Rule |
|---|---|
| NIK (`id.nik`) | Strip non-digits. Must be 16 digits. |
| BPJS (`id.bpjs`) | Strip non-digits. Length 10–16. |
| Phone (`phone.e164`) | Canonical `+` + digits. Country code required. |
| Email (`email`) | Trim and lowercase. |
| Passport (`passport…`) | Alphanumeric, uppercase, spaces removed. |
| MRN | Trim and collapse whitespace. **Not** assumed numeric. Organization/system specific. |
| Other | Trim only. No global lowercasing. |

## Verification

Statuses: `UNVERIFIED`, `VERIFIED`, `REJECTED`, `EXPIRED`.

Existence is not trust. Verification records who, when, how, source, organization, and provenance.

## Uniqueness (database enforced)

Active identifiers (`valid_to IS NULL` and status not `REJECTED`/`EXPIRED`):

- Global: unique `(identifier_system, normalized_value)` where `organization_id IS NULL`.
- Organization-scoped: unique `(identifier_system, organization_id, normalized_value)` where `organization_id IS NOT NULL`.

Concurrent inserts rely on these indexes plus transactions. `SELECT` then `INSERT` is not the safety mechanism.

## API exposure

List and read responses mask sensitive identifiers (NIK, BPJS, passport, national ID, phone, email). Example: `********3456`. Full values are not returned by Wave 1 APIs.
