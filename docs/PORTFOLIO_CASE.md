# Portfolio Case: Trusted A2A Procurement Platform

## One-liner

Спроектирован и реализован демонстрационный MVP доверенной A2A-платформы B2B-закупок, где агент Сбера A3 оркестрирует RFQ, сбор оферт от A2-поставщиков, deterministic ranking, human approval, создание заказа, черновика платежа, документов и evidence trail.

## Problem

Корпоративная закупка обычно размазана между ERP, почтой, каталогами поставщиков, согласованиями, платежами, ЭДО, логистикой и аудитом. Агентные системы могут ускорить координацию, но enterprise-контур не может отдавать LLM право на финансовые или юридически значимые действия.

## Architecture Summary

Система использует три роли:

- **A1 — агент клиента**: формирует закупочную потребность, ограничения, бюджет, сроки и мандат.
- **A2 — агент поставщика**: публикует Agent Card, принимает RFQ и возвращает проверяемую оферту.
- **A3 — доверенный агент Сбера**: валидирует мандат, выбирает поставщиков, отправляет RFQ, нормализует оферты, применяет hard constraints, ранжирует предложения, требует подтверждение человека и ведёт Deal Ledger.

## Key Architecture Decisions

- A3 является trusted control plane, а не чат-ботом.
- LLM используется опционально для extraction/explanation, но не принимает authoritative financial/legal decisions.
- Hard constraints и ranking вычисляются детерминированно.
- Human-in-the-loop обязателен до award/payment draft.
- Approval snapshot hash фиксирует существенные условия, которые подтвердил человек.
- SQL outbox фиксирует бизнес-сообщения до публикации наружу.
- Deal Ledger и evidence bundle позволяют восстановить ход сделки.
- Onboarding внешних A2 вынесен в конфигурацию и registry, а не зашит в workflow.

## What Was Built

- Backend API for A3.
- Independent A1 client-agent.
- Multiple A2 supplier-agent runtimes.
- LangGraph-based orchestration.
- Deterministic ranking and hard constraints.
- PostgreSQL persistence with SQLite fallback.
- Append-only Deal Ledger.
- SQL outbox.
- Evidence bundle.
- MCP tools.
- React/TypeScript frontend.
- Docker Compose demo contour.
- Tests for API, approval, ranking, contracts, frontend, MCP and onboarding.

## Why It Matters

Проект показывает, как AI agents могут участвовать в enterprise-транзакциях без нарушения границ полномочий, аудита, безопасности и человеческой ответственности.

## Architectural Value

Этот MVP демонстрирует не только код, но и архитектурное мышление:

- separation of control plane and data plane;
- explicit authority boundaries;
- reproducible decisions;
- audit-first design;
- safe agent-to-agent interaction;
- readiness for ERP, payments, EDO and bank-product integrations.
