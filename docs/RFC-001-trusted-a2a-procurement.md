# RFC-001: Trusted A2A Procurement Platform

## Status

Draft

## Context

Enterprise procurement включает закупочную потребность, проверку мандата, выбор поставщиков, RFQ, сравнение оферт, согласование, заказ, черновик платежа, документы, статусы исполнения и аудит.

AI agents могут автоматизировать координацию между участниками, но система не должна делегировать LLM полномочия на юридически или финансово значимые действия.

## Problem

Нужно построить A2A-контур, в котором агенты могут безопасно обмениваться структурированными запросами и офертами, а доверенный банковский агент A3 обеспечивает:

- проверку полномочий;
- control plane сделки;
- сопоставимое сравнение оферт;
- human approval;
- auditability;
- подготовку банковских действий без автономного исполнения платежа.

## Goals

- A1 передаёт закупочную потребность, ограничения и мандат.
- A3 проверяет мандат и выбирает активных A2-поставщиков.
- A3 отправляет RFQ нескольким A2.
- A2 возвращают структурированные оферты.
- A3 применяет hard constraints и deterministic ranking.
- Человек подтверждает выбранные существенные условия.
- A3 создаёт order, payment draft, document refs и fulfillment timeline.
- Deal Ledger и evidence bundle позволяют восстановить ход сделки.

## Non-goals

- Нет автономного проведения платежа.
- Нет автономного подписания договора.
- Нет открытого discovery непроверенных A2 в MVP.
- Нет LLM-controlled ranking.
- Нет скрытого изменения условий после approval.
- Нет production-интеграции с реальными банковскими системами в demo-контуре.
- Нет обработки сложных товаров, требующих инженерного подбора.

## Proposed Architecture

```text
Frontend / ERP
     ↓
A1 client-agent
     ↓ A2A task: procurement intent + mandate
A3 Sber trusted agent
     ├─ Mandate / policy validation
     ├─ Supplier discovery via registry
     ├─ Parallel RFQ to A2 suppliers
     ├─ Quote normalization
     ├─ Hard constraints
     ├─ Deterministic ranking
     ├─ Approval snapshot
     ├─ Human approval
     ├─ Award / rejection outbox messages
     ├─ Order + payment draft + document refs
     └─ Deal Ledger + evidence bundle
     ↓
A2 supplier agents
```

## Key Design Decisions

### 1. A3 as trusted control plane

A3 owns orchestration, policy enforcement, audit, approval boundary and integration lifecycle. A3 is not just a conversational agent.

### 2. Deterministic policy and ranking

Hard constraints and ranking are computed by deterministic business logic. LLM may extract data or explain an already computed result, but it does not produce the authoritative decision.

### 3. Human-in-the-loop before award and payment draft

Financially and legally significant actions require explicit human approval. Approval is stored with actor, mandate, selected quote and snapshot hash.

### 4. Approval snapshot hash

Before acceptance, A3 fixes material terms in an approval snapshot. The approval request must refer to this hash so that accepted terms cannot be silently changed.

### 5. SQL outbox for external business messages

Award, rejection, payment and document-related messages are persisted before publication. This supports replay, audit and failure recovery.

### 6. Modular monolith for MVP

The MVP is implemented as a modular monolith with clear domain/service/integration/workflow boundaries. This reduces delivery complexity while preserving future service decomposition options.

## Alternatives Considered

| Alternative | Why not for MVP |
|---|---|
| Direct A1-to-A2 negotiation | Weak control, weaker audit, difficult policy enforcement |
| Fully autonomous LLM agent | Non-reproducible decisions and unacceptable authority boundary |
| Microservices from day one | Adds distributed complexity before validating the vertical scenario |
| LLM-based ranking | Harder auditability and reproducibility |
| Open supplier discovery | Higher fraud/compliance risk for first pilot |

## Trade-offs

- More control and auditability, but less autonomy.
- Faster MVP delivery via modular monolith, but less independent scaling.
- Closed supplier registry reduces marketplace flexibility, but lowers trust risk.
- Deterministic ranking requires explicit policy design, but makes decisions reproducible.
- Human approval slows full automation, but preserves legal and financial accountability.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---:|---|
| Fake supplier endpoint | High | Closed registry, Agent Card validation, endpoint allowlist |
| Budget leakage | High | RFQ redaction, field-level sharing rules |
| Quote tampering after approval | High | Approval snapshot hash, evidence bundle |
| Double order creation | Critical | Idempotency keys, unique business keys |
| Expired or invalid mandate | Critical | Mandate validation before RFQ/award |
| LLM extraction error | Medium | Deterministic validation and human review |
| External message failure | High | SQL outbox, replay, correlation IDs |

## Open Questions

- How should Agent Cards be signed and rotated?
- How should external A2 providers be certified?
- How should ranking policy versions be governed?
- Which fields can be shared with A2 without leaking buyer strategy?
- What is the target integration boundary for real payment execution?
- How should post-award disputes and claims be modeled?

## Future Evolution

- Signed Agent Cards.
- Supplier risk scoring.
- Policy version governance.
- Controlled external discovery.
- ERP, EDO and payment production adapters.
- Bank products: guarantee, factoring, escrow, credit pre-check.
- Vertical packs for different procurement categories.
