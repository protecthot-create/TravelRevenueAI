# TravelRevenueAI — Project Continuity Rules

## Project
TravelRevenueAI

Workspace:
C:\Users\WORK_BOOK\Desktop\TravelRevenueAI

Repository:
https://github.com/protecthot-create/TravelRevenueAI

## Current Git state
Current branch: main

Latest commit:
9669d74 CS7: Add Morning Brief read API

Previous commit:
d04143b RC5: Complete CS1-CS6 backend MVP

Existing tag:
v0.5.0-rc1

CS7 commit has already been pushed to origin/main.

Working tree was verified clean after the CS7 commit.

## Completed work

CS1-CS6:
Complete backend MVP.

CS7:
Morning Brief Read API.

CS7 consists of:

### Repository layer
File:
backend/src/travel_revenue_ai/repositories/morning_brief_repository.py

Read capabilities:
- get persisted MorningBrief by ID
- list MorningBrief history by agency
- load DecisionCards by persisted IDs while preserving persisted order
- deterministic history ordering:
  created_at DESC
  brief_id DESC
- pagination through limit/offset
- read-only repository methods

### Service layer
Files:
backend/src/travel_revenue_ai/services/morning_brief_read_service.py
backend/src/travel_revenue_ai/services/morning_brief_read_errors.py

Service:
MorningBriefReadService

Dataclasses:
MorningBriefReadResult
MorningBriefHistoryItem

Typed errors:
MorningBriefReadError
MorningBriefReadNotFoundError
MorningBriefReadIntegrityError
MorningBriefReadPersistenceError

Important behavior:
- ownership protection
- foreign-agency brief is returned as not found
- persisted card IDs are validated
- persisted card ordering is preserved
- missing DecisionCard causes integrity error
- card agency ownership is validated
- main_decision_card_id integrity is validated
- history reads metadata/counts only
- service is read-only
- no commit
- no rollback
- no flush
- no pipeline invocation
- no Revenue Intelligence execution

### DTO/API layer
File:
backend/src/travel_revenue_ai/schemas/morning_brief_read.py

Read-only public DTOs intentionally exclude:
- snapshots
- idempotency metadata
- execution metadata
- audit metadata
- score breakdown
- ORM objects

Endpoints:

GET /api/v1/morning-brief/{brief_id}

GET /api/v1/agencies/{agency_id}/morning-briefs

HTTP behavior:
- not found / ownership -> 404
- integrity error -> 409
- read-only GET endpoints only

### Runtime wiring
File:
backend/src/travel_revenue_ai/composition.py

Factory:
build_morning_brief_read_service(session)

The API endpoints use the composition factory and request-scoped DB session.

### Tests
File:
backend/tests/test_morning_brief_read_api.py

CS7 focused API tests passed:
7 passed

Other verified checks:
- py_compile passed
- git diff --check passed
- runtime wiring AST check passed
- monkeypatch seam check passed

## CS7 boundary

CS7 is COMPLETE.

Do not redo CS7 unless a future task explicitly requires a correction.

Do not start CS8 unless explicitly instructed.

## Development safety rules

Before modifying production code:
1. Inspect existing architecture and patterns.
2. Identify the exact files allowed to change.
3. Do not modify unrelated files.
4. Do not introduce migrations unless explicitly required.
5. Do not modify frontend unless explicitly required.
6. Do not modify scheduler/source collection unless explicitly required.
7. Do not modify Revenue Intelligence unless explicitly required.
8. Preserve read/write boundaries.
9. Preserve existing persistence contracts.
10. Prefer minimal changes over refactoring.

For database work:
- PostgreSQL is the canonical database.
- Alembic is used for migrations.
- Never invent a migration without an explicit requirement.
- Never change persistence behavior implicitly.

For tests:
- Prefer focused tests first.
- Do not claim tests passed unless actually executed.
- Report warnings separately from failures.
- Do not hide environment/tooling blockers.

For Git:
- Never amend previous commits unless explicitly instructed.
- Never force-push.
- Never create or modify tags unless explicitly instructed.
- Before committing, inspect staged files.
- Do not include unrelated files in commits.
- Keep commits scoped to the requested change.

## Current status

CS7 complete and pushed to GitHub.

Next development phase:
CS8 — NOT STARTED.

Do not begin CS8 automatically.
