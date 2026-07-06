# ADR-0003: Require Human Approval Before Award

## Status

Accepted

## Context

Award, order creation and payment draft preparation are financially and legally significant steps. Enterprise AI systems must preserve accountability and avoid autonomous critical actions.

## Decision

A3 must require explicit human approval before sending award/rejection business messages and before creating downstream order/payment artifacts.

## Consequences

### Positive

- Clear accountability.
- Reduced legal and financial risk.
- Better alignment with enterprise governance.
- Safer MVP for banking context.

### Negative

- Lower autonomy.
- User confirmation adds a step to the workflow.
- Requires approval UI/API and audit records.

## Alternatives

- Fully autonomous award.
- Auto-award under threshold.
- Manual procurement without agent recommendation.
