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
