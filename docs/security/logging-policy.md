# Logging policy

Application logs are for troubleshooting. Audit events are for accountability. They are not the same stream.

## Required fields when available

`timestamp`, `level`, `service`, `environment`, `correlation_id`, `request_id`, `module`, `event`

## Never log

- passwords
- access or refresh tokens
- API keys and storage secrets
- database URLs
- full medical records, notes, or documents
- NIK or other national identifiers unless a later legal policy explicitly requires a redacted form

A redaction processor strips known secret keys from structlog events. Do not put PHI in log `event` strings.

## Production format

JSON to stdout. Local debug may use a console renderer.
