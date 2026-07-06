# ADR-0004: Use Approval Snapshot Hash

## Status

Accepted

## Context

The user must approve exact material terms: supplier, item, quantity, price, delivery, warranty and related constraints. If quote data changes after the UI is rendered, the approval could bind different terms than the user saw.

## Decision

Before approval, A3 creates an approval snapshot and computes a snapshot hash. The approval request must reference this hash. A3 accepts approval only if the current snapshot hash matches the approved hash.

## Consequences

### Positive

- Prevents silent modification of accepted terms.
- Improves auditability.
- Makes approval evidence stronger.
- Helps detect stale UI or changed quote data.

### Negative

- Adds extra state and validation.
- Requires hash versioning if snapshot schema changes.

## Alternatives

- Approve by quote ID only.
- Approve by current database state.
- Approve by UI state without backend hash.
