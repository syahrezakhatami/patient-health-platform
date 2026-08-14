# Matching policy

## Search is not matching

- **Search:** “find a patient I am allowed to see.” Wave 1 does not expose name search or a global directory.
- **Matching:** “do these two identity representations refer to the same person?” `POST /api/v1/mpi/match`.

## Safety rule

False-positive identity matching is more dangerous than false-negative matching.

**When uncertain: do not merge.** Create a match candidate or require human review.

A score is evidence, not truth. Wave 1 never auto-merges.

These are different things and must stay different:

- `score` ≠ merge
- `score` ≠ identity confirmation
- `score` ≠ authorization
- `score` ≠ clinical access

Only an explicit, authorized `POST /api/v1/mpi/merge` mutates identity lifecycle or cluster membership.

## Engine

`DeterministicMatchingEngine`, algorithm version `deterministic-v1`.

The interface accepts a probe and stored identities and returns `MatchResult` (`candidate_patient_id`, `score`, `confidence`, `decision`, `reasons`, `evidence`, `algorithm_version`).

Probabilistic / ML / embedding matching is out of scope. The engine class is the extension point for a later wave.

## Deterministic rules

| Evidence | Decision | Score | Notes |
|---|---|---|---|
| Same identifier as a stored **verified** identifier, same system, same ownership scope | `CONFIRMED_MATCH` | 1.0 | Probe need not already be verified. Name equality is not required. |
| Distinct verified identifiers in the same system/scope | `NO_MATCH` | 0.0 | Same name + DOB does not override this. |
| Same unverified identifier | `REQUIRES_REVIEW` | 0.5 | Not trusted enough to confirm. |
| Same unverified identifier + name + DOB | `REQUIRES_REVIEW` | 0.55 | Still not a merge. |
| Same normalized name + birth date, no trusted identifier | `POSSIBLE_MATCH` | 0.4 | Duplicate-name case. Never merge. |
| Organization-scoped MRN compared across organizations | no result | — | Same MRN string is not a global person. |

`PROBABLE_MATCH` is reserved and unused in v1.

## Minimum match criteria

An identity id, at least one identifier, or name **and** birth date. Name-only matching is rejected to limit enumeration.

## Canonical identity resolution

Matching never treats a `MERGED` row as its own target.

If the probe includes `identity_id` and that identity is `MERGED`, the service walks `surviving_identity_id` to the canonical active identity (maximum 8 hops). Historical identifiers on merged rows remain attached and are compared against the survivor. The match result references the survivor UUID.

Resolution fails safely (`409 canonical_resolution_failed`) when:

- the chain cycles
- `surviving_identity_id` is missing
- a hop is `RETIRED`
- the row does not exist

The matcher itself also skips `MERGED` and `RETIRED` stored identities. It does not mutate lifecycle, cluster, or merge history.

## Candidate persistence

Pair matches (probe includes a stored `identity_id`) continue to upsert `identity_match_candidates`.

Probe-only evaluation (identifier or name+DOB without a stored identity) persists insert-only `identity_match_probes`:

- `PROBE_ONLY` when no persistable candidate exists
- `MATCHED_CANDIDATE` when a decision other than `NO_MATCH` is produced

Stored fields: candidate UUID (if any), actor, organization, facility, purpose, matcher version, evidence types, score, decision, timestamp, provenance, correlation ID.

Raw NIK, BPJS, passport, phone, and email are not stored on the probe. A probe does not create a patient identity, grant access, confirm identity, or merge.
