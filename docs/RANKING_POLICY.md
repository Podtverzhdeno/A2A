# Ranking Policy v1

## Purpose

Ранжировать оферты поставщиков воспроизводимо, объяснимо и без скрытого изменения критериев во время сделки.

## Authority Boundary

Hard constraints and ranking are authoritative only when computed by deterministic business logic.

LLM may:

- extract structured fields from free-form text;
- generate explanation for already computed ranking;
- help user understand rejected quotes.

LLM must not:

- select the winning supplier as the authoritative decision;
- override hard constraints;
- change weights or policy version during a deal;
- approve award, payment or contract terms.

## Inputs

- `quote_id`.
- `supplier_id`.
- `unit_price`.
- `quantity`.
- `total_price`.
- `currency`.
- `vat`.
- `delivery_date`.
- `warranty_months`.
- `quote_ttl`.
- `supplier_risk`.
- `mandate`.
- `buyer_constraints`.
- `ranking_weights`.

## Hard Constraints

A quote is rejected before scoring if:

- supplier is not active in registry;
- category is not allowed by mandate;
- quantity or unit does not match RFQ;
- total price exceeds maximum allowed amount;
- delivery date is later than required date;
- quote is expired;
- currency is unsupported;
- required documents or warranty data are missing.

## Scoring Dimensions

Suggested scoring dimensions for MVP:

- price score;
- delivery score;
- warranty score;
- supplier risk penalty;
- completeness score.

## Example Formula

```text
final_score =
    price_score      * W_price
  + delivery_score   * W_delivery
  + warranty_score   * W_warranty
  + completeness     * W_completeness
  - risk_penalty     * W_risk
```

## Versioning

Each ranked deal must store:

- `ranking_policy_version`;
- normalized quote inputs;
- hard constraint results;
- score components;
- final score;
- rejected quote reasons;
- selected quote ID;
- approval snapshot hash.

## Explainability

A3 must be able to explain:

- why a quote was rejected;
- why the selected quote won;
- which criteria affected score most;
- which policy version was used.
