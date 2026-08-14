# Merge and unmerge policy

Merge is a high-risk identity-graph operation. It is **not** `DELETE A` and rewrite foreign keys to `B`.

Wave 1 has no clinical rows. The merge design still forbids destructive rewrite so later waves can keep `patient_id` immutable on clinical facts.

## Merge: A into B

1. Authenticate.
2. Authorize `mpi.merge.execute` through the PDP (deny by default).
3. Require an explicit reason, actor / organization context, and structured evidence (one or more items). Each item must include `evidence_type`, `evidence_source`, `evidence_reference`, `reviewer_reason`, and `reviewed_at`. Allowed types: `VERIFIED_IDENTIFIER`, `DOCUMENT_REVIEW`, `PATIENT_CONFIRMATION`, `FACILITY_RECORD`, `STAFF_REVIEW`, `OTHER`. Empty evidence, missing reason, or an unknown type is `422`. Evidence must not contain raw NIK/BPJS/passport/phone/email. Historical merge rows are left unchanged.
4. Reject self-merge, retired identities, merge into an already-merged target, and cycles.
5. If the source is already merged into the same target, return the existing operation (idempotent).
6. Evaluate identifier conflicts. Same system + same ownership + different active values → **stop**. Do not guess.
7. Insert `identity_merge_operations` (`MERGE`, `COMPLETED`).
8. Set source `lifecycle_status = MERGED` and `surviving_identity_id = B`.
9. Move cluster membership. Do not delete the source identity or its identifiers.
10. Write audit (`PATIENT_MERGED`, `IDENTITY_STATUS_CHANGED`) and provenance.

Idempotency keys (`idempotency_key`) prevent duplicate operations on retry.

Concurrent merge of the same source into different targets is serialized with `SELECT FOR UPDATE` on both identity rows (locked in UUID order to avoid deadlock). The second transaction re-reads lifecycle after the lock and is rejected if the source is already merged. Unmerge uses the same lock so two concurrent unmerges cannot both succeed.

## Unmerge

Unmerge is not “set status back to ACTIVE.”

1. Authorize `mpi.unmerge.execute`.
2. Load the original `MERGE` row. It remains in history forever.
3. Confirm the source is `MERGED` into the recorded target.
4. Insert a new `UNMERGE` row pointing at the original merge (`related_merge_id`).
5. Restore source to `ACTIVE`, clear `surviving_identity_id`.
6. Close merged cluster membership and create a new singleton cluster.
7. Audit and provenance. No history is rewritten or deleted.

## History protection

`identity_merge_operations` and `identity_provenances` are insert-only (database triggers). Foreign keys from history to identities use `ON DELETE RESTRICT`. There is no identity delete API.
