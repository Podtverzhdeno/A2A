# Реализованный демонстрационный MVP

## Компоненты

- `a2a-client-agent` — независимый A1, принимающий запрос frontend и
  передающий потребность A3 через официальный A2A SDK 1.x.
- `a2a-api` — A3: mandate policy, discovery, параллельный RFQ, hard
  constraints, ranking, approval, REST, A2A и MCP.
- `a2a-supplier` — переиспользуемый runtime A2; три экземпляра запускаются с
  разными каталогами и Agent Card.
- React frontend — история сделок, live Deal Ledger, оферты, ranking и
  подтверждение.
- PostgreSQL в Docker Compose; SQLite является локальным fallback.

## Реальный агентный обмен

```text
Frontend → A1 REST
A1 → A3 A2A Task + structured data part
A3 → A2.1/A2.2/A2.3 A2A Task + RFQ data part
A2 → A3 Quote Artifact
A3 → A1 persisted deal state + SSE events
```

Agent Card, JSON-RPC route, Task, status update и Artifact создаются официальным
пакетом `a2a-sdk`.

## Постоянное состояние

SQL-хранилище содержит:

- сделки;
- отдельный append-only Deal Ledger;
- организации;
- регистрации внешних агентов;
- snapshot Agent Card.

Alembic применяет миграции до запуска A3 в Docker Compose. Незавершённые сделки
в статусе `draft` повторно ставятся в выполнение после старта A3.

## Внешний onboarding

```text
POST /api/v1/admin/organizations
GET  /api/v1/admin/organizations
POST /api/v1/admin/agents
GET  /api/v1/admin/agents
```

При регистрации A3:

1. проверяет существование организации;
2. загружает Agent Card внешнего endpoint;
3. проверяет обязательные поля;
4. сохраняет регистрацию;
5. добавляет RemoteSupplierAgent в discovery registry.

## Заменяемые интеграции

- `OrderGateway` → сейчас `MockOrderGateway`;
- `SupplierRiskGateway` → сейчас `MockSupplierRiskGateway`;
- supplier catalog → сейчас mock-каталог внутри соответствующего A2;
- identity → сейчас явно обозначенный demo identity header;
- payment → создаётся только `PaymentDraft`;
- OpenRouter/GigaChat → необязательный `LanguageModelService`.

Mock order/payment и risk не находятся внутри workflow: будущие production-
адаптеры реализуют те же интерфейсы.

## LLM

Провайдер выбирается только через environment:

```dotenv
LLM_PROVIDER=disabled
```

или:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=...
OPENROUTER_MODEL=...
```

или:

```dotenv
LLM_PROVIDER=gigachat
GIGACHAT_CREDENTIALS=...
GIGACHAT_MODEL=...
GIGACHAT_SCOPE=...
```

Ошибка или timeout LLM приводит к детерминированному fallback и не меняет
результат ranking.

## Надёжность demo

- supplier timeout;
- ограниченный retry;
- partial success при достаточном числе оферт;
- постоянная история;
- SSE timeline;
- доверенный supplier risk со стороны A3;
- повторное подтверждение возвращает существующий заказ;
- один `order_id` и один `payment_draft_id` на сделку;
- URL сделки восстанавливается после обновления браузера.

## Осознанные mock-границы

MVP не выполняет:

- реальный платёж;
- юридически значимую подпись;
- production OIDC/mTLS;
- реальный KYB/AML;
- интеграцию с ERP/ЭДО/логистикой Сбера.

Эти возможности подключаются через новые реализации integration ports либо
через внешний совместимый A1/A2 endpoint. Изменение доменного workflow для
замены mock-адаптера не требуется.
