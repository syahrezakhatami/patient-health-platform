# Manual Vital Signs — Provider Clinical-Safety Hazard Register

**Date:** 2026-08-30  
**Kind:** PROVIDER CLINICAL-SAFETY HAZARD REGISTER — engineering evidence  
**Implementation baseline:** `39909b44a1bad737839b9267a068d8bb0fa0b389` (uncommitted working tree)  
**Provider catalog:** `manual-vitals-mvp-v1`  
**Planned capability:** `manual_vital_signs_write` @ `1.0.0` (not registered)

Human clinical-risk acceptance is **not** recorded in this document. Disposition column values are engineering verification status only unless a separate signed human review record exists.

---

## Register

| ID | Scenario | Potential harm | Cause | Engineering control | Verification evidence | Residual risk | Human-review disposition |
|----|----------|----------------|-------|---------------------|----------------------|---------------|--------------------------|
| MV-H-001 | Measurement written to wrong patient | Wrong clinical record; treatment on wrong person | Client-supplied patient id trusted; encounter mismatch | `expected_patient_identity_id` precondition; encounter-derived binding; same-person MPI validation; wrong-patient 404 conceal; RETIRED 409; no client persisted patient authority | `test_wrong_patient_matrix`, `test_merged_identity_persists_historical_patient`, `test_retired_identity_denies` | Site SOP for patient selection remains required | **PENDING HUMAN REVIEW** |
| MV-H-002 | Measurement written under wrong organization | Cross-tenant data exposure | Org header / principal scope error | `Principal.for_organization`; org membership; cross-org 404 conceal; DB org bindings on observation | `test_cross_org_manual_vitals_concealed`, `test_encounter_cross_org_denies`, `test_multi_org_principal_switch_no_context_bleed` | Credential sharing / workstation policy outside software | **PENDING HUMAN REVIEW** |
| MV-H-003 | Measurement attributed to wrong facility | Facility-level reporting/authorization error | Header omission widens scope; wrong facility grant | Frozen facility matrix; encounter facility; actor facility authorization; empty `actor_facility_ids` = all current-org facilities only | `test_facility_matrix` | Site facility assignment SOP | **PENDING HUMAN REVIEW** |
| MV-H-004 | Write to invalid encounter state | Clinically inappropriate timing (e.g. cancelled visit) | Encounter status not enforced | `IN_PROGRESS` provider-safe; `CANCELLED`/`ENTERED_IN_ERROR` hard reject; `PLANNED`/`FINISHED` site policy | `test_encounter_status_matrix`, `test_cancelled_encounter_hard_reject_despite_planned_allow`, `test_planned_encounter_denied_when_policy_missing_allow` | Site may allow PLANNED/FINISHED per policy — not universal | **PENDING HUMAN REVIEW** |
| MV-H-005 | Wrong LOINC / measurement semantics | Mislabeled vital in record | Client submits arbitrary code/unit | Static server catalog; `measurement_key` only; five keys; provider catalog version binding; POST extra fields forbidden | `test_post_extra_fields_forbidden`, `test_measurement_key_spoofing_rejected`, unit `test_manual_vitals_domain.py` | UI label localization must not change semantics | **PENDING HUMAN REVIEW** |
| MV-H-006 | Wrong unit recorded | Dose/measurement misinterpretation | User enters value in non-canonical unit | Server-owned canonical UCUM; no unit selector; no conversion; client unit rejected | Catalog source; hardening decimal tests | **User must enter value matching displayed canonical unit** — workflow limitation | **PENDING HUMAN REVIEW** |
| MV-H-007 | Silent numeric rounding / float drift | Clinically material precision loss | Binary float; unbounded scale | `Decimal`; `Numeric(14,4)`; scale/precision validation; NaN/Infinity rejection | `test_decimal_exponent_notation_rejected`, `test_oversized_numeric_string_rejected`, unit decimal tests | Extreme values recorded if technically valid — see MV-H-015 | **PENDING HUMAN REVIEW** |
| MV-H-008 | Duplicate measurement on retry/double-click | Duplicate clinical facts | Network retry; concurrent submit | `Idempotency-Key`; canonical semantic fingerprint; PostgreSQL race handling; replay re-validates current auth/policy | `test_concurrent_same_key_one_observation`, `test_concurrent_same_key_exact_row_counts`, `test_idempotency_same_key_same_semantic_value` | Operator must use consistent idempotency key on intentional re-submit | **PENDING HUMAN REVIEW** |
| MV-H-009 | Write under stale governance | Feature used after suspension/revocation | Readiness cached without lock | `_resolve_write_readiness_for_mutation()` with `FOR UPDATE` on provider, profile header, activation; full layer re-resolution | `test_provider_suspend_mid_flow_denies_post`, `test_site_suspend_mid_flow_denies_post`, `test_stale_profile_subset_denies_post_after_republish`, boundary TOCTOU tests | Ordering: write-before-suspend commit is valid if lock held through commit | **PENDING HUMAN REVIEW** |
| MV-H-010 | Provider kill-switch bypass | Writes after provider SUSPENDED | TOCTOU on provider state | Provider row lock; SUSPENDED/RETIRED hard deny; deterministic concurrency ordering | `test_concurrent_provider_suspend_and_manual_vital_post`, `test_provider_row_lock_blocks_concurrent_suspend`, `test_provider_suspended_denies` | None identified at engineering layer if locks honored | **PENDING HUMAN REVIEW** |
| MV-H-011 | Site activation bypass | Org uses feature without site approval | Missing activation/policy | Feature ACTIVE required; activation row lock/recheck; profile policy; approval scope; deployment gates | `test_production_dark_fail_closed_without_site_activation`, `test_deployment_gate_missing_denies`, site TOCTOU tests | Site must complete Gate C separately | **PENDING HUMAN REVIEW** |
| MV-H-012 | Forged / stale approval evidence | Unauthorized clinical write | Approval scope mismatch | Org binding; feature ID/version; `governance_profile_version_id`; `CLINICAL_GOVERNANCE` type; scope SHA-256; immutable published policy | `test_approval_forgery_wrong_scope_denies`, `test_approval_forgery_wrong_feature_version_denies`, `test_profile_version_binding_denies_stale_approval`, `test_scope_hash_collision_not_authority_without_binding` | Human approval evidence quality depends on site process | **PENDING HUMAN REVIEW** |
| MV-H-013 | Generic Observation OGP bypass (GENERIC-OBS-001) | Vital recorded without governed workflow | Same actor used `POST /clinical/observations` + `VITAL_SIGNS` | **RESOLVED:** `ClinicalService.create_observation()` rejects `VITAL_SIGNS` with 403 `vital_signs_requires_governed_route`; Manual Vitals uses trusted internal persistence | `test_generic_vital_signs_staff_create_blocked_without_ogp`, `test_production_dark_both_routes_fail_closed`, `test_generic_exam_observation_still_allowed` | SECURITY COMPATIBILITY CORRECTION vs Wave 2B.2a public write | **PENDING HUMAN REVIEW** |
| MV-H-014 | Stale frontend context | Submit after patient/org switch | Client holds old selection | Server authority at submit; patient/org/facility state clearing; late-response guards; no localStorage authority | `manual-vital-write.test.tsx` race/org-switch tests | Training on patient verification | **PENDING HUMAN REVIEW** |
| MV-H-015 | Abnormal but technically valid value recorded | Clinically surprising value without alert | No interpretation layer | **Explicit product boundary:** software records measurement; does **not** validate clinical normality or provide diagnostic interpretation | Design contract; no normal-range tests added | **Operational reliance on clinician judgment** | **PENDING HUMAN REVIEW** |
| MV-H-016 | PHI persisted locally | Device compromise exposure | Browser storage of vitals | Memory-only form state; no localStorage/sessionStorage/IndexedDB for values; mutation `retry=false` | Frontend source scan; security hardening tests | Shared workstation policy outside software | **PENDING HUMAN REVIEW** |
| MV-H-017 | Audit/provenance not written with mutation | Weakened accountability | Partial commit | Successful mutation + audit/provenance in same transaction | `test_success_audit_and_provenance_metadata`, `test_zz_audit_failure_rolls_back_observation` | Inherited platform P2: DENIED audit rollback (separate from success path) | **PENDING HUMAN REVIEW** |
| MV-H-018 | Incorrect clinical time semantics | Wrong timeline in chart | Naive timestamps; backdating abuse | `effective_at` = client measurement time; `recorded_at` = server time; offset-aware contract; naive rejected | `test_naive_effective_at_rejected`, `test_effective_at_timezone_semantic_replay` | Backdating tolerance = **SITE_CLINICAL_POLICY** | **PENDING HUMAN REVIEW** |
| MV-H-019 | Temperature site/method misrepresentation | Wrong clinical interpretation of temperature | Generic LOINC 8310-5 without site | MVP uses generic 8310-5 + Cel only; **no** oral/axillary/tympanic/rectal capture; UI must not imply site/method | Pre-implementation contract §3.3; UI uses generic label only | **Semantic/usability limitation** — site SOP must define entry convention | **PENDING HUMAN REVIEW** |
| MV-H-020 | Erroneous value not corrected in UI | Persistent wrong vital in chart | Correction UI deferred | Backend Observation amend/EIE exists for Wave 2B.2a; Healthcare Web exposes **create-only** Manual Vitals form | Wave 2B.2a observation amend tests (backend); no Manual Vitals correction UI | **Operational correction dependency** — site must use existing backend correction paths or SOP | **PENDING HUMAN REVIEW** |
| MV-H-021 | BP / SpO2 attempted via product | Unsupported paired/pulse-ox semantics | Scope creep | BP and SpO2 **explicitly excluded** from provider catalog and UI | Catalog source (five entries only); design deferral docs | N/A if exclusions honored | **PENDING HUMAN REVIEW** |
| MV-H-022 | Displayed unit does not match selected measurement | Operator enters a value using the wrong canonical unit | UI inferred unit from first catalog entry while `measurementKey` was empty or unmatched | Exact key lookup (`boundMeasurement`); no unit unless selected key matches a catalog object; POST still server-derives LOINC/UCUM | `boundMeasurement.test.ts`; first-paint / five-entry / subset UI tests | Residual: operator must still match the displayed unit once selected | **PENDING HUMAN REVIEW** |

---

## Resolved engineering findings (historical)

| ID | Type | Summary |
|----|------|---------|
| GENERIC-OBS-001 | **P1 product defect → RESOLVED** | Same-actor generic `VITAL_SIGNS` bypass; fixed at application service boundary |
| MV-TOCTOU-001 | **P1 hardening → RESOLVED** | Governance row-lock recheck before mutation |
| MV-REG-001 | **Test defect** | `row_version` helper loop in governance tests — fixed in regression closure |
| MV-REG-002 | **Test defect** | Idempotency replay policy re-check — fixed in regression closure |
| MV-REG-003 | **Test harness** | Wave 2B tests using generic `VITAL_SIGNS` after security correction — updated |
| MV-REG-004 | **P3 test reliability** | `test_iam_shell_context_hardening::test_success_reads_do_not_audit_or_write_provenance` — one flaky full-suite occurrence; passes isolated; four subsequent full suites green |
| MV-UI-001 | **UI semantic defect on candidate v1 → RESOLVED in v2** | Displayed unit fell back to `measurements[0]` while `measurementKey` was not authoritative. v1 tag frozen/not eligible for approval. |

---

## Temperature limitation (explicit)

| Aspect | MVP behavior |
|--------|----------------|
| LOINC | `8310-5` Body temperature |
| Unit | `Cel` (canonical) |
| Not captured | Measurement site (oral, axillary, tympanic, rectal, etc.) |
| Not captured | Measurement method/device |
| UI requirement | Generic label only — no site/method implication |
| Classification | Product semantic limitation — not a hidden clinical claim |

---

## Correction pathway residual risk

| Layer | Status |
|-------|--------|
| Backend Wave 2B.2a | Observation amend and entered-in-error APIs exist |
| Manual Vitals dedicated UI | **Create-only** — no amend/EIE/correction workflow |
| Healthcare Web | No correction controls in Observations Manual Vitals form |
| Site dependency | Correction policy, authorized roles, and operational workflow **PENDING** per organization |

This residual risk must be presented to the human provider clinical reviewer. Engineering does **not** classify it acceptable.
