# Anonymous patient identity

A person may need care before NIK, MRN, BPJS, phone, or email can be established.

## Creation

`POST /api/v1/mpi/identities/anonymous`

- Generates an opaque UUID.
- Sets `lifecycle_status = ANONYMOUS`.
- Human label: `UNKNOWN-{8 hex}` or `TEMP-{8 hex}` when `temporary=true`.
- No demographic or identifier fields are required.
- Audit: `ANONYMOUS_IDENTITY_CREATED`.
- Provenance records the creating organization, actor, and source system when provided.

Encounter association is a later wave. Wave 1 only creates the identity mechanism.

## Resolution

Anonymous identities are **not** silently merged into an identified person.

Two explicit operations exist:

1. **Identify in place** — `POST /api/v1/mpi/identities/{id}/identify`  
   Same UUID becomes `ACTIVE`. Identifiers may be added. Reason is required. History of the anonymous period remains.

2. **Resolve into an existing person** — explicit `MERGE` of the anonymous identity into the surviving identity.  
   The anonymous row is retained as `MERGED`.

## Flow

```
anonymous UUID created
        │
        ├─ later identified as a new person
        │     → identify-in-place → ACTIVE (same UUID)
        │
        └─ later identified as an existing person
              → explicit MERGE → MERGED, surviving_identity_id set
```
