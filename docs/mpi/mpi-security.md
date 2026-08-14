# MPI security

## Authentication

All MPI routes require a valid JWT (Wave 0 OIDC/JWT validator). Unprovisioned subjects are denied.

## Authorization

Every sensitive operation goes through `Wave1PolicyPDP`. Unknown actions remain deny-by-default.

Permissions are codes such as `mpi.identity.create` and `mpi.merge.execute`. The PDP does not inspect role names (`doctor` is meaningless here).

Organization scope is an authorization concern. Membership is loaded into the authorization context. Database filters are an enforcement layer, not the whole model.

Platform scope (`iam.platform`) is required for cross-organization administration. A registrar at Hospital B does not automatically read Hospital A identities.

## Facility scope

Empty `actor_facility_ids` means the membership is **organization-wide**: every facility in that already-authorized organization is in scope. It is **not** unrestricted platform access. Organization scope is evaluated first. When a membership binds specific facilities, those IDs are an allow-list.

## Purpose of use

`X-Purpose` is required on MPI routes and is recorded on audit events. It is **not** an authorization grant. Values are allow-listed and normalized (trim, uppercase, `-`/` ` → `_`):

`REGISTRATION`, `IDENTITY_RESOLUTION`, `EMERGENCY`, `CARE_COORDINATION`, `ADMINISTRATION`, `PATIENT_ACCESS`, `AUDIT`, `SYSTEM_OPERATION`.

Missing, empty, or unknown purpose returns `422`. A valid purpose without the required permission is still denied by the PDP.

## Patient enumeration

There is no `GET /patients?name=`. Name-only match is rejected. Lookup requires an identifier. Unauthorized or unknown reads return `404` to reduce existence oracles. Rate limiting from Wave 0 still applies. Purpose (`X-Purpose`) is required.

## Identifier masking

Sensitive identifiers are masked in API responses. Full NIK / passport / BPJS values are not returned. Audit metadata stores type and decision, not the raw identifier.

## Cross-organization MPI

Hospital B may submit a match probe. A match decision is not a grant of clinical access. Wave 1 has no clinical records.

## Audit vs provenance

- Audit: who did what, when, and why (`audit_events`).
- Provenance: where the assertion came from (`identity_provenances`).

They are separate tables.
