# ADR-0002: Keep Ranking Deterministic

## Status

Accepted

## Context

Supplier quote selection affects money, obligations and audit. LLM-generated decisions are difficult to reproduce and may change across model versions, prompts or providers.

## Decision

Hard constraints and ranking are calculated by deterministic business logic. LLM may parse free-form text and explain the result, but it does not produce the authoritative ranking.

## Consequences

### Positive

- Ranking is reproducible.
- Audit is simpler.
- Business rules can be tested.
- Human approver can inspect exact criteria.

### Negative

- Less flexible than fully LLM-based reasoning.
- Requires explicit policy design.
- New ranking dimensions require versioned policy changes.

## Alternatives

- LLM chooses best supplier.
- Human manually compares all offers.
- Supplier marketplace chooses ranking.
