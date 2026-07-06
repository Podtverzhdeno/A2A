# ADR-0005: Use SQL Outbox for Business Messages

## Status

Accepted

## Context

A3 sends business messages to external agents and adapters: award, rejection, payment draft, document and fulfillment-related events. External calls can fail after local state changes.

## Decision

A3 stores outbound business messages in SQL outbox before publishing them. Workers or service logic can publish and retry messages while preserving auditability.

## Consequences

### Positive

- Avoids losing business messages.
- Supports replay.
- Improves audit trail.
- Makes partial failure handling explicit.

### Negative

- Requires outbox table and processing logic.
- Delivery is at-least-once, so consumers must be idempotent.
- Requires monitoring for stuck messages.

## Alternatives

- Direct HTTP calls after state change.
- Message broker only, without SQL persistence.
- Manual resend from logs.
