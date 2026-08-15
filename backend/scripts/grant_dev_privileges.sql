-- Apply after `alembic upgrade head` in local/dev only.
-- Production grants must be managed by operations, not copied from these passwords.
-- Required for the Docker backend, which connects as app_dml.

GRANT USAGE ON SCHEMA public TO app_dml, app_audit_insert, readonly, migrator;
GRANT CREATE ON SCHEMA public TO migrator;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_dml;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_dml;

REVOKE UPDATE, DELETE, TRUNCATE ON TABLE audit_events FROM app_dml;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE identity_merge_operations FROM app_dml;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE identity_provenances FROM app_dml;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE identity_match_probes FROM app_dml;
REVOKE UPDATE, DELETE, TRUNCATE ON TABLE clinical_provenances FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE encounters FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE clinical_notes FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE encounter_participants FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE conditions FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE observations FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE laboratory_orders FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE laboratory_specimens FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE laboratory_results FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE medications FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE allergies FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE consents FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE immunizations FROM app_dml;
REVOKE DELETE, TRUNCATE ON TABLE procedures FROM app_dml;
GRANT INSERT, SELECT ON TABLE audit_events TO app_dml;
GRANT INSERT, SELECT ON TABLE identity_merge_operations TO app_dml;
GRANT INSERT, SELECT ON TABLE identity_provenances TO app_dml;
GRANT INSERT, SELECT ON TABLE identity_match_probes TO app_dml;
GRANT INSERT, SELECT ON TABLE clinical_provenances TO app_dml;
GRANT INSERT, SELECT ON TABLE audit_events TO app_audit_insert;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly;

-- Tables in this workspace are created by php_admin (Alembic) or migrator.
ALTER DEFAULT PRIVILEGES FOR ROLE php_admin IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_dml;
ALTER DEFAULT PRIVILEGES FOR ROLE php_admin IN SCHEMA public
    GRANT SELECT ON TABLES TO readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE migrator IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_dml;
ALTER DEFAULT PRIVILEGES FOR ROLE migrator IN SCHEMA public
    GRANT SELECT ON TABLES TO readonly;
