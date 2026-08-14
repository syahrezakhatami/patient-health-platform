# Canonical identity resolution

The persisted identity row is never deleted after merge. The authoritative identity for matching is the canonical active survivor.

## Walk

```
identity.id
  → if MERGED, follow surviving_identity_id
  → repeat (max 8 hops)
  → stop on ACTIVE or ANONYMOUS
```

`RETIRED` is not matchable. A missing hop, a self-reference, or a cycle returns no canonical identity. The matcher then fails safely (`409`) instead of inventing a target.

## Matching consequences

- A `MERGED` identity is not a separate match target.
- Historical identifiers on the merged row remain and are compared through the survivor.
- Match results reference the survivor UUID.
- The matcher does not write lifecycle, cluster, `surviving_identity_id`, identifiers, or merge history.

## What this is not

Canonical resolution is not automatic merge, not identity confirmation, and not authorization.
