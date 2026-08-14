# Purpose-of-use catalog

`X-Purpose` is required on MPI and other organization-scoped identity routes. It records why an actor requested the operation. It is **not** an authorization grant.

The PDP remains the only authorization authority. Application services must not write `if purpose == ...` as a substitute for permission checks.

## Allowed values

| Purpose | Typical use |
|---|---|
| `REGISTRATION` | Create or identify a patient identity during registration |
| `IDENTITY_RESOLUTION` | Match, verify, merge, unmerge, or review candidates |
| `EMERGENCY` | Emergency anonymous registration or identity lookup |
| `CARE_COORDINATION` | Cross-facility identity coordination (identity only) |
| `ADMINISTRATION` | Administrative identity read |
| `PATIENT_ACCESS` | Reserved for later patient-facing identity access |
| `AUDIT` | Auditor identity read |
| `SYSTEM_OPERATION` | System/operator identity maintenance |
| `TREATMENT` | Wave 2A clinical encounter and note authorship |

## Normalization

Input is stripped, uppercased, and `-` / space are converted to `_`. `registration`, `REGISTRATION`, and `Registration` are the same value. Unknown values return `422`.

Missing or empty `X-Purpose` returns `422`.

## What purpose does not do

- It does not grant a permission.
- It does not bypass organization or facility scope.
- It does not confirm identity or trigger merge.
- It does not create clinical access.

Purpose is stored on audit events and on `identity_match_probes`.
