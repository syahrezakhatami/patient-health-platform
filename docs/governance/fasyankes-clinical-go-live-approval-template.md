# Fasyankes clinical go-live approval template

**Date:** 2026-08-28
**Kind:** SITE ACTIVATION TEMPLATE — all human fields default PENDING
**Baseline:** `c55d259180c4864b56ea40e4c24833c9cd438d68`
**Hardening gate:** `docs/gates/provider-governance-hardening-gate.md`

Reusable for **hospital · clinic · Puskesmas**. Shared platform; organization-specific policy profile.
Vendor implementation alone does **not** activate clinical write / AI features.

Not legal advice. Do not invent mandatory committee names — use **role categories** with named approver fields left PENDING until real humans sign.

Gate type: **`SITE_APPROVAL_PENDING`** until complete · **`DEPLOYMENT_GATE`** for controller/processor evidence.

---

## 1. Scope

| Field | Value |
|---|---|
| Organization id / name | PENDING |
| Facility id / name | PENDING |
| Facility type | hospital / clinic / Puskesmas / other — PENDING |
| Feature / capability | PENDING |
| Product / catalog version | PENDING |
| Environment | staging / production — PENDING |
| Requested go-live date | PENDING |

---

## 2. Configuration

| Item | Value / version | Status | N/A reason (if N/A) |
|---|---|---|---|
| Terminology catalog version | PENDING | PENDING | |
| Permission grants reviewed | PENDING | PENDING | |
| Encounter status policy (PLANNED / FINISHED etc.) | PENDING | PENDING | |
| Late-entry / backdating policy | PENDING | PENDING | |
| Correction policy (who / when / reason) | PENDING | PENDING | |
| AI use cases enabled | NONE / list — PENDING | PENDING | |
| Clinical AI restrictions | PENDING | PENDING | |
| Site Clinical Policy Profile version | PENDING | PENDING | |
| SATUSEHAT / interoperability readiness | PENDING | PENDING | |
| Backup / recovery verified | PENDING | PENDING | |

---

## 3. Privacy / security / deployment

| Item | Evidence ref | Status | N/A reason |
|---|---|---|---|
| Controller/processor role assessment (`PRIV-002`) | PENDING | PENDING | |
| DPA executed | PENDING | PENDING | |
| Subprocessors disclosed | PENDING | PENDING | |
| Privacy / security review | PENDING | PENDING | |
| Staff training on privacy/security | PENDING | PENDING | |
| Deployment approval (technical) | PENDING | PENDING | |

Unresolved controller/processor assessment → **`DEPLOYMENT BLOCKED`** (not platform P1).

---

## 4. Training & UAT

| Item | Evidence | Status | N/A reason |
|---|---|---|---|
| Staff training completed | PENDING | PENDING | |
| Clinical SOP for feature | PENDING | PENDING | |
| UAT scenarios executed | PENDING | PENDING | |
| Clinical acceptance testing | PENDING | PENDING | |
| Known defects accepted? | PENDING | PENDING | |
| Rollback plan understood | PENDING | PENDING | |

Clinical feature without SOP/training → **site go-live blocked**.

---

## 5. AI go-live (if applicable — else mark N/A)

| Item | Evidence | Status |
|---|---|---|
| Intended use reviewed | PENDING | PENDING / N/A |
| `AI_REGULATORY_APPLICABILITY` assessed | NOT_ASSESSED default | PENDING / N/A |
| TEVV passed | PENDING | PENDING / N/A |
| Model/version pinned | PENDING | PENDING / N/A |
| Human oversight defined | PENDING | PENDING / N/A |
| Fallback verified | PENDING | PENDING / N/A |
| Kill switch tested | PENDING | PENDING / N/A |
| Incident owner assigned | PENDING | PENDING / N/A |
| Site AI acceptance | PENDING | PENDING / N/A |

---

## 6. Sign-offs (names default PENDING — real humans only)

| Role category | Name | Date | Decision |
|---|---|---|---|
| Site product / IT owner | PENDING | PENDING | PENDING |
| Medical / clinical governance representative | PENDING | PENDING | PENDING |
| Medical record / RMIK representative | PENDING | PENDING | PENDING |
| Privacy / security representative | PENDING | PENDING | PENDING |
| Facility leadership (where required) | PENDING | PENDING | PENDING |

Decisions: APPROVED / REJECTED / DEFERRED.

---

## 7. Release conditions

- [ ] P0 = 0 for this feature in release evidence
- [ ] Provider P1 = 0 unresolved for production activation
- [ ] Required technical tests passed
- [ ] Regulatory applicability assessed if AI/clinical risk
- [ ] Terminology approved where required
- [ ] Controller/processor assessment complete (`DEPLOYMENT_GATE`)
- [ ] Security/privacy review complete
- [ ] Observability / audit available
- [ ] Rollback available
- [ ] Core EMR works without AI if AI feature
- [ ] SATUSEHAT/interoperability evidence where applicable
- [ ] Backup/recovery verified

Unknown / not-applicable states must be explicit — do not leave blank without N/A reason.

---

## 8. Final site decision

```
SITE GO-LIVE DECISION = PENDING
DEPLOYMENT APPROVAL BY = PENDING
DEPLOYMENT APPROVAL DATE = PENDING
```

PASS requires named, dated, versioned evidence — not merely that this template exists.
