# IAM model

Wave 1 IAM is the staff identity foundation required for MPI and organization administration. It is not a clinical RBAC catalog.

## Entities

| Entity | Meaning |
|---|---|
| User | Provisioned platform actor mapped from JWT `sub`. |
| Role | Named permission bundle (`PLATFORM_ADMIN`, `ORG_ADMIN`, `REGISTRAR`, `IDENTITY_OFFICER`, `AUDITOR`). |
| Permission | Action/scope code such as `mpi.merge.execute`. |
| Organization membership | User + optional organization + optional facility + role. |

A user may belong to many organizations and may hold different roles in each.

## Authorization model

Controllers do not decide access. Application services call the PDP with:

- actor
- permission code (`action`)
- organization / facility / patient
- purpose
- emergency context slot (unused in Wave 1)

Default remains deny. Permission *definitions* live in the application catalog (`Permission`, `ROLE_PERMISSIONS` seed map). Runtime role → permission *assignment* is read from `role_permissions`. Removing an assignment in the database denies that permission even if the seed map still lists it.

Do not write `if user.role == "doctor"`. The PDP evaluates permission codes, organization membership, and facility scope. Purpose-of-use is audit context only; it never grants authorization.

## Roles (Wave 1)

| Role | Intent |
|---|---|
| `PLATFORM_ADMIN` | All Wave 1 permissions, including `iam.platform`. |
| `ORG_ADMIN` | Membership, facilities, organization identifiers, identity read. |
| `REGISTRAR` | Create identities, add identifiers, evaluate matches. |
| `IDENTITY_OFFICER` | Verify, review matches, merge, unmerge. |
| `AUDITOR` | Read-only, including Wave 2A encounter/note read. |
| `CLINICIAN` | Create encounters, author and finalize clinical notes. |

Wave 2A clinical permissions are codes such as `clinical.encounter.create`. They are not a substitute for consent or a FHIR API.

## Facility membership semantics

A membership with `facility_id = NULL` is organization-wide. The PDP treats an empty facility binding list as “all facilities in the authorized organization,” not “all facilities on the platform.” Organization isolation still applies.
