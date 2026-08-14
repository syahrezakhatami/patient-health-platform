-- Local development role model. Passwords are synthetic and must never be used in production.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE ROLE migrator LOGIN PASSWORD 'migrator_dev_only';
CREATE ROLE app_dml LOGIN PASSWORD 'app_dml_dev_only';
CREATE ROLE app_audit_insert LOGIN PASSWORD 'app_audit_insert_dev_only';
CREATE ROLE readonly LOGIN PASSWORD 'readonly_dev_only';

GRANT CONNECT ON DATABASE php_dev TO migrator, app_dml, app_audit_insert, readonly;
GRANT USAGE ON SCHEMA public TO migrator, app_dml, app_audit_insert, readonly;
GRANT CREATE ON SCHEMA public TO migrator;
GRANT CREATE ON DATABASE php_dev TO migrator;
