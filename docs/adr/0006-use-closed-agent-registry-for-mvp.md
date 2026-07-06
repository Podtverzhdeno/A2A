# ADR-0006: Use Closed Agent Registry for MVP

## Status

Accepted

## Context

Open discovery of external supplier agents increases fraud, compliance and quality risks. The MVP needs to prove the procurement lifecycle before solving open-market trust.

## Decision

MVP uses a closed registry of approved A2 suppliers. Each supplier registration stores organization data, endpoint, capabilities and Agent Card snapshot.

## Consequences

### Positive

- Lower onboarding risk.
- Easier debugging and demo reliability.
- Clear trust assumptions.
- Better control over supplier capabilities.

### Negative

- Less marketplace-like.
- Requires admin onboarding flow.
- Does not yet solve open A2 discovery.

## Alternatives

- Open internet discovery.
- Manual hardcoded suppliers only.
- Third-party marketplace discovery.
