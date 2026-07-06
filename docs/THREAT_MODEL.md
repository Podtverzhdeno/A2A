# Threat Model: Trusted A2A Procurement Platform

## Assets

- Procurement intent.
- Mandate.
- Supplier registry.
- Agent Card snapshots.
- RFQ messages.
- Supplier quotes.
- Ranking inputs and outputs.
- Approval snapshot.
- Order ID.
- Payment draft ID.
- Document references.
- Deal Ledger.
- SQL outbox messages.
- Evidence bundle.

## Trust Boundaries

1. Frontend / ERP → A1.
2. A1 → A3.
3. A3 → A2 supplier agents.
4. A3 → LLM provider.
5. A3 → payment adapter.
6. A3 → EDO/document adapter.
7. A3 → persistence layer.
8. Admin onboarding API → Agent Registry.

## Threats

| Threat | Example | Impact | Mitigation |
|---|---|---:|---|
| Fake supplier | Malicious endpoint pretends to be A2 | High | Closed registry, Agent Card validation, allowlist |
| Budget leakage | A2 receives max budget or buyer strategy | High | RFQ redaction, field-level sharing policy |
| Quote tampering | Supplier changes terms after approval | High | Approval snapshot hash, evidence bundle |
| Replay attack | Old award message is resent | High | message_id, timestamp, causation_id, idempotency key |
| Double order | Retry creates duplicate order | Critical | unique business key, idempotent award/order creation |
| Unauthorized approval | Wrong actor approves selected quote | Critical | mandate validation, approved_by, role checks |
| Expired quote accepted | Quote TTL passed before award | High | quote expiration validation before approval/award |
| LLM hallucination | Wrong SKU/category/quantity extracted | Medium | LLM outside authority boundary, deterministic validation |
| Supplier data leakage | A2 sees competitor quotes | High | isolated quote storage and response shaping |
| Outbox loss | Business message not sent after state change | High | SQL outbox, retry, replay tooling |
| Admin misuse | Untrusted A2 registered by mistake | High | admin authorization, audit, review workflow |

## Security Principles

- LLM is outside the authority boundary.
- No critical financial/legal action without human approval.
- Every state-changing command must be auditable.
- Every external business message must have correlation ID.
- Every accepted quote must be bound to approval snapshot hash.
- Supplier quotes must be isolated from competitors.
- Registry changes must be auditable.

## MVP Controls

- Closed supplier registry.
- Deterministic ranking.
- Approval snapshot hash.
- Deal Ledger.
- SQL outbox.
- Correlation IDs.
- Mock payment/document adapters.

## Target Production Controls

- mTLS between agents.
- OAuth2 client credentials for service-to-service access.
- Signed Agent Cards.
- Signed critical messages.
- Short-lived tokens.
- Key rotation and revocation.
- Replay protection with nonce/timestamp.
- Fine-grained RBAC/ABAC for admin operations.
- Security monitoring and anomaly detection.
