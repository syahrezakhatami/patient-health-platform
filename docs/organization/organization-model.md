# Organization model

An organization is a healthcare institution or owning body. It is not hardcoded as `HOSPITAL`.

## Types

`HOSPITAL`, `CLINIC`, `LABORATORY`, `PHARMACY`, `NETWORK`, `OTHER`.

## Facility

A facility is a physical or logical location operated by an organization.

Fields: name, code (unique per organization), type, optional `address_text`, status, `organization_id`.

Facility types include hospital site, clinic site, laboratory site, emergency department, pharmacy site, and other. Clinical departments and staff rosters are out of Wave 1.

## Organization identifiers

External identifiers use `identifier_system` + `identifier_value` with a system-specific `normalized_value`. There is no single global organization identifier format.

## Users

Users associate to organizations and optional facilities through IAM memberships, not through clinical staff entities.

## Isolation

Organization context must be explicit (`X-Organization-Id` on org-scoped APIs). A user is not implicitly authorized for every organization.
