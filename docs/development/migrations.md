# Migrations

Alembic is the only schema-change path. The API process does not auto-migrate on startup.

## Commands

From `backend/`:

```bash
alembic upgrade head
alembic downgrade -1
alembic revision -m "describe_the_change"
```

Use `DATABASE_MIGRATION_URL` (migrator / admin) for Alembic. The application uses `DATABASE_URL` (`app_dml`).

After `alembic upgrade head` in local/dev, apply `scripts/grant_dev_privileges.sql` as the admin role. Alembic does not grant DML. The Docker backend connects as `app_dml` and will return `internal_error` / `permission denied` until grants exist. Re-run the script after new tables (for example `identity_match_probes` in `20260813_0003`).

## Environments

| Environment | Who runs migrations | When |
|---|---|---|
| local | developer, explicitly | after pull / before integration tests |
| staging | CI or operator, explicitly | before promoting the app |
| production | operator, explicitly | change window; never from app boot |

Never `DROP TABLE`, `DROP COLUMN`, or `TRUNCATE` from application startup.

## Wave 0 schema

`audit_events` is insert-only (trigger + intended grants). Do not edit `20260813_0001`.

## Wave 1 schema

Migration `20260813_0002` adds IAM, organization, and MPI identity tables. It does not add encounter or other clinical tables. History tables (`identity_merge_operations`, `identity_provenances`) are insert-only.

Wave 1.5 concurrent merge/unmerge safety is enforced by row locks on `patient_identities` plus the existing single `surviving_identity_id` column. A unique “one completed MERGE per source forever” index was rejected because unmerge must allow a later explicit re-merge while leaving the original MERGE row immutable.

## Wave 1.5 MPI hardening schema

Migration `20260813_0003` adds insert-only `identity_match_probes` for auditable probe-only matching. It does not add encounter or other clinical tables. Do not edit `20260813_0001` or `20260813_0002`. Do not run destructive downgrade against a populated local database.

## Wave 2A clinical foundation schema

Migration `20260814_0004` adds `encounters`, `encounter_participants`, `clinical_notes`, and `clinical_provenances`. It does not add diagnosis, medication, laboratory, or FHIR tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new tables.

Migration `20260814_0005` hardens Wave 2A history: encounter rows cannot be deleted, encounter `patient_identity_id` is immutable, and FINAL / ENTERED_IN_ERROR clinical notes cannot revert or have author/content rewritten. Do not edit `0001`–`0003`. Do not run destructive downgrade against a populated local database.

## Wave 2B.1 Condition schema

Migration `20260814_0006` adds `conditions` (problem-list item and encounter diagnosis). It does not add observation, medication, laboratory, allergy, or FHIR tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new table and so DELETE remains revoked. Do not edit `0001`–`0005`. Do not run destructive downgrade against a populated local database.

Migration `20260814_0007` is additive Condition integrity only: `conditions.provenance_id` → `clinical_provenances.id` `ON DELETE RESTRICT`, and the Condition history trigger also freezes onset, abatement, recorded time, facility, and provenance. It does not change Encounter or clinical-note schema. Do not edit `0001`–`0006`. Do not run destructive downgrade against a populated local database.

## Wave 2B.2a Observation schema

Migration `20260814_0008` adds `observations` (native measurements/findings). It does not add laboratory, medication, allergy, or FHIR tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new table and so DELETE remains revoked. Do not edit `0001`–`0007`. Do not run destructive downgrade against a populated local database.

## Wave 2B.2b Laboratory schema

Migration `20260814_0009` adds `laboratory_orders`, `laboratory_specimens`, and `laboratory_results`. It extends `clinical_provenances.subject_type` with laboratory subjects and seeds laboratory permissions. It does not add medication, allergy, consent, or FHIR tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new tables and so DELETE remains revoked. Do not edit `0001`–`0008`. Do not run destructive downgrade against a populated local database.

## Wave 2B.3a Medication schema

Migration `20260814_0010` adds `medications`. It extends `clinical_provenances.subject_type` with `MEDICATION` and seeds medication permissions. It does not add allergy, consent, prescription, administration, or FHIR tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new table and so DELETE remains revoked. Do not edit `0001`–`0009`. Do not run destructive downgrade against a populated local database.

## Wave 2B.3b Allergy schema

Migration `20260814_0011` adds `allergies`. It extends `clinical_provenances.subject_type` with `ALLERGY` and seeds allergy permissions. It does not add consent, FHIR AllergyIntolerance, or later clinical tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new table and so DELETE remains revoked. Do not edit `0001`–`0010`. Do not run destructive downgrade against a populated local database.

## Wave 2B.3c Consent schema

Migration `20260814_0012` adds `consents`. It extends `clinical_provenances.subject_type` with `CONSENT` and seeds consent permissions. It does not add FHIR Consent, break-glass, patient-portal, or later clinical tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new table and so DELETE remains revoked. Do not edit `0001`–`0011`. Do not run destructive downgrade against a populated local database.

## Wave 2B.4 Immunization schema

Migration `20260814_0013` adds `immunizations`. It extends `clinical_provenances.subject_type` with `IMMUNIZATION` and seeds immunization permissions. It does not add Procedure, CarePlan, FHIR Immunization, schedule, inventory, or registry tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new table and so DELETE remains revoked. Do not edit `0001`–`0012`. Do not run destructive downgrade against a populated local database.

## Wave 2B.5 Procedure schema

Migration `20260814_0014` adds `procedures`. It extends `clinical_provenances.subject_type` with `PROCEDURE` and seeds procedure permissions. It does not add CarePlan, FHIR Procedure, order, schedule, inventory, or registry tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new table and so DELETE remains revoked. Do not edit `0001`–`0013`. Do not run destructive downgrade against a populated local database.

## Wave 2B.6 Medical Device schema

Migration `20260814_0015` adds `medical_devices`. It extends `clinical_provenances.subject_type` with `MEDICAL_DEVICE` and seeds medical-device permissions. It does not add FHIR Device, inventory, Patient History, Adverse Event, VitalSign, CarePlan, or later clinical tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new table and so DELETE remains revoked. Do not edit `0001`–`0014`. Do not run destructive downgrade against a populated local database.

## Wave 2B.7 Adverse Event schema

Migration `20260814_0016` adds `adverse_events`. It extends `clinical_provenances.subject_type` with `ADVERSE_EVENT` and seeds adverse-event permissions. Optional FKs to `medications`, `medical_devices`, and `procedures` are additive on `adverse_events` only. It does not add FHIR AdverseEvent, pharmacovigilance, incident-management, Patient History, VitalSign, CarePlan, or later clinical tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new table and so DELETE remains revoked. Do not edit `0001`–`0015`. Do not run destructive downgrade against a populated local database.

## Wave 2B.8 Family History schema

Migration `20260814_0017` adds `family_histories`. It extends `clinical_provenances.subject_type` with `FAMILY_HISTORY` and seeds family-history permissions. It does not add FHIR FamilyMemberHistory, Patient History, relative identity, Condition FK, CarePlan, or later clinical tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new table and so DELETE remains revoked. Do not edit `0001`–`0016`. Do not run destructive downgrade against a populated local database.

## Product access and tenancy foundation schema

Migration `20260814_0018` adds `patient_accounts` (1:1 UUID bind to `patient_identities.id`, never NIK/BPJS), seeds `patient.account.read` and `patient.record.read`, and strips `clinical.*` / `mpi.*` (and other non-retained) grants from `PLATFORM_ADMIN`. It does not add tenant, subscription, entitlement, AI, scheduling, notification, pharmacy, or patient-history tables. After upgrade, re-run `scripts/grant_dev_privileges.sql` so `app_dml` can use the new table and so DELETE remains revoked. Do not edit `0001`–`0017`. Do not run destructive downgrade against a populated local database.
