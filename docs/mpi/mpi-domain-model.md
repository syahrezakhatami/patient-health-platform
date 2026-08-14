# MPI domain model

Master Patient Index (MPI) is the Wave 1 identity domain. It answers “who is this person?” It does **not** store clinical history.

## What MPI means

MPI is the platform representation of a real-world person who may receive care from multiple organizations. The internal primary key is an opaque UUID (`patient_identities.id`). NIK, BPJS, MRN, passport, phone, email, and name are attributes, never keys.

## What MPI does not mean

MPI is not:

- an MRN
- a hospital registration record
- a clinical chart
- a FHIR Patient resource store
- a license to read another organization’s clinical data

Identity matching and clinical data access are separate concerns. Wave 1 establishes identity only.

## Entities

| Concept | Persistence | Meaning |
|---|---|---|
| Person | Conceptual | The real-world human. Not a second table. |
| Patient identity | `patient_identities` | Platform identity. This **is** the person record. |
| Patient identifier | `patient_identifiers` | An identifier belonging to that identity. |
| Identity cluster | `identity_clusters` + `identity_cluster_members` | Controlled grouping of identities believed to be one person. |
| Match candidate | `identity_match_candidates` | Evidence that two stored identities may be the same person. Never an automatic merge. |
| Match probe | `identity_match_probes` | Insert-only evidence of a probe-only resolution attempt. Does not create an identity. |
| Merge / unmerge | `identity_merge_operations` | Explicit, durable link operations. Source rows are not deleted. |
| Provenance | `identity_provenances` | Where an identity assertion came from. |

## Design answers

1. **Internal patient ID** — `patient_identities.id` (UUID).
2. **Real-world person** — represented by a patient identity; after merge, the cluster’s canonical / surviving identity is authoritative.
3. **External identifiers** — `patient_identifiers.identifier_system` + `identifier_value`.
4. **MRN** — an organization-owned identifier (`identifier_type = MRN`, `organization_id` required).
5. **Identifier ownership** — `organization_id` / `facility_id` on the identifier. Hospital A MRN and Hospital B MRN are different identifiers.
6. **Identifier provenance** — `identity_provenances` plus `source_system` / `source_record_id` on the identifier.
7. **Verification** — `verification_status` (`UNVERIFIED`, `VERIFIED`, `REJECTED`, `EXPIRED`) plus method, actor, and timestamp. Not a boolean.
8. **Anonymous identity** — `lifecycle_status = ANONYMOUS`, no required identifiers.
9. **Duplicate candidates** — `identity_match_candidates`.
10. **Merges** — `identity_merge_operations` with `MERGE` / `UNMERGE`. Source identity remains, status `MERGED`.

## Cluster semantics

A cluster is not a generic tag table. It records which identities are currently treated as one person.

- Created automatically when an identity is created (singleton cluster).
- Merge moves the source into the target cluster as `MERGED_IN` and closes the source’s previous active membership.
- Unmerge closes the merged membership and creates a new singleton cluster for the restored identity.
- Source identity rows and historical memberships are retained.

Who can modify a cluster: only merge / unmerge / identify operations after PDP authorization (`mpi.merge.execute`, `mpi.unmerge.execute`, or identity resolution). There is no generic cluster CRUD API.

## Rule enforcement

| Rule | Enforced by |
|---|---|
| Identifier uniqueness (global / org-scoped) | DATABASE (partial unique indexes) |
| Valid enum values, no self-merge row, required FKs, UUID PKs | DATABASE |
| Insert-only merge history and provenance | DATABASE (triggers) |
| Lifecycle transition graph | APPLICATION |
| Merge validation (already merged, cycles, identifier conflicts, reason, structured evidence) | APPLICATION |
| Identifier normalization and masking | APPLICATION |
| Matching decisions (never auto-merge) | APPLICATION |
| Create / verify / match / merge / unmerge permission | PDP |
| Organization and facility scope | PDP (membership in authorization context) |
