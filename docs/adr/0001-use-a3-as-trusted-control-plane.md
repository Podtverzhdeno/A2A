# ADR-0001: Use A3 as Trusted Control Plane

## Status

Accepted

## Context

A2A procurement requires coordination between buyer intent, supplier RFQ, mandate validation, ranking, approval, order, payment draft, documents and audit.

If A1 and A2 communicate directly without a trusted coordinator, policy enforcement, evidence collection and financial/legal boundaries become harder to guarantee.

## Decision

A3 acts as the trusted control plane and transaction coordinator for MVP.

A3 owns:

- mandate validation;
- supplier discovery;
- RFQ orchestration;
- hard constraints;
- deterministic ranking;
- approval snapshot;
- Deal Ledger;
- outbox messages;
- evidence bundle.

## Consequences

### Positive

- Clear trust boundary.
- Centralized audit.
- Easier enforcement of buyer policies.
- Easier integration with banking services.

### Negative

- A3 becomes a critical component.
- More responsibility in one platform layer.
- Requires strong reliability and observability.

## Alternatives

- Direct A1-to-A2 negotiation.
- Marketplace-style broker without banking control plane.
- Fully decentralized supplier discovery and negotiation.
