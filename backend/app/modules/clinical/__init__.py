"""Clinical bounded context.

Wave 2A: Encounter and clinical note.
Wave 2B.1: Condition (problem list and encounter diagnosis).
Wave 2B.2a: native Observation (measurements/findings).
Wave 2B.2b: native Laboratory (order, specimen, result).
Wave 2B.3a: native Medication (prescribed or reported medication fact).
Wave 2B.3b: native Allergy (documented allergy/intolerance fact).
Wave 2B.3c: native Consent (documented permit/refuse decision).

Does not own FHIR, PDP enforcement, or later clinical domains.
"""
