# Identity lifecycle

Wave 1 identity status is **not** clinical status, registration status, or encounter status.

## States

| State | Meaning |
|---|---|
| `ANONYMOUS` | Real-world identity is not established. Care may still occur in later waves. |
| `ACTIVE` | Authoritative identified identity. |
| `MERGED` | No longer authoritative. `surviving_identity_id` points to the surviving identity. Row is retained. |
| `RETIRED` | Withdrawn without a surviving identity. Terminal in Wave 1. |

`IDENTIFIED` is not a stored state. Identification is the transition `ANONYMOUS → ACTIVE` on the same UUID, or an explicit merge of an anonymous identity into an existing person.

`RETIRED` is terminal. There is no Wave 1 API that reactivates a retired identity. Active identifiers on a retired row still occupy uniqueness slots until they are expired or rejected; reuse requires that explicit identifier change, not silent revival.

Matching resolves `MERGED` identities to the canonical survivor before comparison. See [canonical-resolution.md](canonical-resolution.md).

## Allowed transitions

```
ANONYMOUS → ACTIVE
ANONYMOUS → MERGED
ANONYMOUS → RETIRED
ACTIVE    → MERGED
ACTIVE    → RETIRED
MERGED    → ACTIVE     (unmerge only)
RETIRED   → (none)
```

Arbitrary transitions are rejected by application rules (`assert_transition`). Database CHECK constraints limit stored values; they do not encode the full graph.

## Temporary identity

Temporary identities use `identity_kind = TEMPORARY` and a human label `TEMP-{8 hex chars}`. The security identifier is still a UUID. Sequential labels such as `TEMP-001` are not used.
