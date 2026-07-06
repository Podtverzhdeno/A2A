# Demo Script: Trusted A2A Procurement Platform

## Scenario

Покупатель хочет закупить стандартизированный MRO-товар. A1 передаёт потребность и мандат A3. A3 запрашивает несколько A2-поставщиков, сравнивает оферты, требует подтверждение человека и создаёт downstream artifacts.

## Demo Flow

1. Start Docker Compose demo contour.
2. Open frontend.
3. Submit procurement intent from form or free text.
4. A1 sends structured intent and mandate to A3.
5. A3 validates mandate.
6. A3 discovers active A2 suppliers.
7. A3 sends RFQ to 2–3 A2 agents in parallel.
8. A2 agents return structured quotes.
9. A3 validates quote schemas and applies hard constraints.
10. A3 ranks valid quotes deterministically.
11. Frontend shows valid/rejected quotes and ranking explanation.
12. Human approves selected quote.
13. A3 stores approval snapshot hash.
14. A3 sends award to selected A2 and rejection to others.
15. A3 creates order ID, payment draft ID, document refs and fulfillment timeline.
16. Evidence bundle shows full trace of the deal.

## What to Highlight

- A3 is a trusted control plane, not a chatbot.
- LLM is optional and outside the authority boundary.
- Ranking is deterministic and testable.
- Human approval gates financial/legal actions.
- Approval snapshot hash prevents silent changes of accepted terms.
- Deal Ledger and SQL outbox make the process auditable and replayable.
- External A2 onboarding is registry/config driven.

## Success Criteria

- Deal can be created end-to-end.
- At least two suppliers are queried.
- Invalid offers are rejected with reasons.
- Ranking is reproducible.
- Approval creates exactly one order and one payment draft.
- Repeated approval does not create duplicate order.
- Evidence bundle reconstructs the full decision path.
