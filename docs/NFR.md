# Non-Functional Requirements

## Reliability

- State-changing operations must be idempotent.
- Award creation must not create duplicate orders on retry.
- Payment draft creation must be idempotent.
- Supplier timeouts must not block the entire RFQ if enough valid quotes are available.
- External business messages must be persisted before publication.
- Failed outbox messages must be replayable.

## Auditability

- Every deal has a stable `deal_id`.
- Every business event has actor, timestamp, correlation ID and payload hash where applicable.
- Every approval references selected quote and approval snapshot hash.
- Every external message is represented in SQL outbox.
- Evidence bundle must reconstruct the decision path: intent → mandate → RFQ → quotes → constraints → ranking → approval → award → order/payment/documents.

## Security

- No autonomous payment execution in MVP.
- No autonomous contract signing in MVP.
- LLM must not own authority over financial or legal decisions.
- Supplier quotes must not be visible to competing suppliers.
- Registry/onboarding operations must be auditable.
- Sensitive buyer fields must not be shared with A2 unless explicitly allowed by policy.

## Operability

- `/health` indicates liveness.
- `/ready` indicates dependency readiness.
- Logs must include correlation ID.
- Demo reset must be reproducible.
- Failed outbox records must be inspectable.
- The system should support local SQLite fallback and PostgreSQL demo mode.

## Performance Targets for MVP

- Support one buyer and 2–3 suppliers in a demo contour.
- RFQ should be sent to suppliers in parallel.
- Ranking must be reproducible for the same inputs.
- P95 quote comparison latency target for demo mode: under 3 seconds after receiving supplier responses.
- Demo frontend should reflect deal events without manual data transfer.

## Compliance and Governance

- Critical actions require human approval.
- Ranking policy version must be stored with decision artifacts.
- Approval records must be immutable from business perspective.
- Future production integrations must define data retention and evidence retention periods.
