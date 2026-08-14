# Source control readiness

This workspace is the application repository. A `.git` directory was missing at the start of Wave 1.5 final remediation (finding H7).

## What was done

`git init` was run in the project root so the tree is source-control ready. No commit was created. Global Git configuration was not modified.

## Recommended first commit (operator)

After reviewing `.gitignore` (exclude `.env`, `.venv`, caches, and secrets):

```bash
cd /path/to/patient-health-platform
git status
git add -A
git commit -m "Initial Wave 1.5 MPI production-hardening foundation"
```

Do not commit `.env`, credentials, or real patient data.

## Risk if Git remains uninitialized

Without a repository there is no history, no reviewable diff, and no rollback for identity-schema changes. That is an engineering process risk, not an application runtime defect.
