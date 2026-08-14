# File upload security

All uploads are untrusted. Clinical document workflows are not implemented in Wave 0. Future waves must enforce this policy.

## Validate

- extension allow-list
- MIME type
- magic bytes
- size
- filename (metadata only)
- checksum (SHA-256)

## Store

- S3-compatible private bucket
- random object IDs (UUID)
- no user-controlled key or filesystem path
- no public ACL
- quarantine then malware scan before promotion (later wave)
- outside any web root

## Forbid

- path traversal
- executable uploads
- trusting double extensions
- trusting `Content-Type` alone
- exposing raw storage paths to clients

The Wave 0 object-storage abstraction already uses random object IDs, private ACL, size limits, and SHA-256 checksums. Magic-byte and malware scanning arrive with the Documents wave.
