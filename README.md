# Sber A2A Procurement Platform

Проект доверенной A2A-платформы для проведения B2B-закупок через агента Сбера.

## Реализованный MVP

В репозитории работает вертикальный demo-flow:

1. A1 передаёт A3 потребность и мандат.
2. LangGraph workflow A3 параллельно запрашивает три A2-поставщика.
3. Hard constraints и ranking вычисляются детерминированно.
4. OpenRouter или GigaChat опционально разбирает текст и объясняет готовый рейтинг.
5. Уполномоченный человек подтверждает оферту.
6. A3 фиксирует approval snapshot, отправляет demo-award выбранному A2 и
   rejection остальным.
7. A3 создаёт order ID, payment draft ID, mock-документы и fulfillment timeline.
8. REST API, MCP tools и Deal Ledger возвращают состояние, события и evidence.

Сделки, Deal Ledger, организации и регистрации внешних A2 хранятся в SQL:
локально используется SQLite fallback, в Docker Compose — PostgreSQL.

## Быстрый запуск

Требования: Python 3.13 и `uv`.

```powershell
cd C:\Users\user\IdeaProjects\A2A
uv sync --dev
uv run a2a-demo
uv run a2a-api
```

После запуска:

- Swagger UI: `http://127.0.0.1:8000/docs`
- health: `http://127.0.0.1:8000/health`
- readiness: `http://127.0.0.1:8000/ready`
- Agent Card: `http://127.0.0.1:8000/.well-known/agent-card.json`
- MCP: `http://127.0.0.1:8000/mcp/`

Проверки:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\check.ps1
```

Сброс Docker-demo с пересборкой и очисткой volume:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\demo-reset.ps1
```

## LLM: OpenRouter или GigaChat

Основной flow работает без LLM. Для разбора свободного текста и генерации объяснений:

```powershell
Copy-Item .env.example .env
```

Провайдер и модель всегда задаются в локальном `.env`, а не в Python-коде.

OpenRouter:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<ваш ключ>
OPENROUTER_MODEL=<выбранная модель OpenRouter>
```

GigaChat:

```dotenv
LLM_PROVIDER=gigachat
GIGACHAT_CREDENTIALS=<ключ авторизации>
GIGACHAT_MODEL=<доступная модель GigaChat>
GIGACHAT_SCOPE=<scope проекта>
```

`.env` исключён из Git. Мандаты, hard constraints, ranking, approval и создание заказа не делегируются LLM.

## Полный сетевой demo-контур

```powershell
Copy-Item .env.example .env
docker compose up --build
```

После запуска:

- frontend A1: `http://127.0.0.1:8080`;
- A3 API и Swagger: `http://127.0.0.1:8000/docs`;
- A1 API: `http://127.0.0.1:8100/docs`;
- readiness probe A3: `http://127.0.0.1:8000/ready`;
- PostgreSQL хранит сделки и Deal Ledger;
- A1 передаёт потребность A3 через официальный A2A SDK;
- A3 параллельно обращается к трём независимым A2 через A2A;
- каждый A2 публикует собственную Agent Card и возвращает Quote Artifact.

Если Docker Desktop не запущен, тот же сетевой контур можно поднять в отдельных
PowerShell-окнах:

```powershell
$env:SUPPLIER_ID="supplier-a"; $env:APP_PORT="8201"; uv run a2a-supplier
$env:SUPPLIER_ID="supplier-b"; $env:APP_PORT="8202"; uv run a2a-supplier
$env:SUPPLIER_ID="supplier-c"; $env:APP_PORT="8203"; uv run a2a-supplier
$env:SUPPLIER_MODE="remote"; $env:APP_PORT="8000"; uv run a2a-api
$env:A3_URL="http://127.0.0.1:8000"; $env:APP_PORT="8100"; uv run a2a-client-agent
```

### Подключение внешнего A2

1. Создайте организацию через `POST /api/v1/admin/organizations`.
2. Передайте её `organization_id`, `agent_id` и внешний `endpoint_url` в
   `POST /api/v1/admin/agents`.
3. A3 загрузит `/.well-known/agent-card.json`, проверит обязательные поля,
   сохранит snapshot Agent Card и активирует RemoteSupplierAgent.

Зарегистрированный endpoint сохраняется в PostgreSQL и восстанавливается после
перезапуска. Поэтому новый совместимый A2 подключается конфигурацией/onboarding,
без изменения workflow A3.

Статус зарегистрированного A2 можно менять через
`PATCH /api/v1/admin/agents/{agent_id}/status`. Активный агент добавляется в
discovery registry, при отключении удаляется из маршрутизации RFQ.

## Что добавлено в текущем hardening-этапе

1. Approval snapshot фиксирует существенные условия выбранной оферты до акцепта.
2. Approval требует `approval_snapshot_hash`, поэтому пользователь подтверждает
   именно показанные ему условия.
3. Deal Ledger получил event UUID, correlation ID, causation ID, message ID и
   hash payload для аудита.
4. SQL outbox сохраняет award, rejection, payment и document messages.
5. Evidence bundle выгружает сделку, ledger, snapshot, order, payment draft,
   fulfillment, documents и outbox.
6. Post-award lifecycle доводит demo-сделку до `completed`.
7. Fulfillment и document refs вынесены за workflow в заменяемые integration ports.
8. `/ready` проверяет готовность SQL-хранилища и наличие supplier registry.
9. Onboarding поддерживает включение и отключение внешнего A2 без изменения кода.
10. Добавлены contract/security-style тесты для Agent Card, demo identity и
    валидации approval payload.

## Ролевая модель

Ролевые обозначения в проекте фиксированы и не должны переиспользоваться в другом смысле:

| Код | Роль | Ответственность |
|---|---|---|
| **A1** | Агент клиента | Формирует потребность покупателя, ограничения, бюджет и критерии выбора; получает результат и инициирует подтверждение |
| **A2** | Агент поставщика | Публикует возможности поставщика и возвращает проверяемые оферты, документы и статусы исполнения |
| **A3** | Агент Сбера | Проверяет мандат, обнаруживает A2, параллельно собирает предложения, нормализует и ранжирует их, организует подтверждение, расчёт, ЭДО и аудит |

Если участвуют несколько поставщиков, их агенты обозначаются `A2.1`, `A2.2`, …, `A2.N`.

Базовый маршрут:

```text
A1 → A3 → A2.1
       ├→ A2.2
       └→ A2.N

A2.1 ─┐
A2.2 ─┼→ A3 → A1
A2.N ─┘
```

A3 не выбирает предложение произвольно. Он применяет критерии и веса, заданные мандатом A1, раскрывает комиссии и объясняет результат. Денежные и юридически значимые действия в MVP подтверждает уполномоченный человек.

## Документация

- [План проекта](docs/PROJECT_PLAN.md) — цели, границы, этапы, команда, backlog, риски и критерии запуска.
- [Архитектура](docs/ARCHITECTURE.md) — компоненты, протоколы, модель данных, безопасность и эксплуатация.
- [Спецификация MVP](docs/MVP_SCOPE.md) — сценарий пилота, пользовательские истории и проверяемые критерии приёмки.

## Предлагаемый первый пилот

Закрытая закупка стандартизированных MRO-товаров:

- один корпоративный покупатель;
- 2–3 заранее аккредитованных поставщика;
- 100–300 стандартизированных SKU;
- действующие рамочные договоры;
- RFQ, сопоставление оферт, выбор, заказ, черновик платежа, ЭДО и статусы поставки;
- обязательное подтверждение человеком перед акцептом и платежом.

## Планируемая структура репозитория

```text
A2A/
├── README.md
├── pyproject.toml
├── docs/
│   ├── PROJECT_PLAN.md
│   ├── ARCHITECTURE.md
│   └── MVP_SCOPE.md
├── src/
│   ├── sber_a2a/
│   │   ├── domain/          # Канонические сущности и бизнес-правила
│   │   ├── application/     # Use cases и state machine сделки
│   │   ├── protocol/        # A2A binding и отраслевые расширения
│   │   ├── adapters/        # ERP, ЭДО, платежи, KYB и поставщики
│   │   ├── api/             # Входной API и callbacks
│   │   └── observability/   # Метрики, трассировка и аудит
│   └── demo_agents/
│       ├── a1_client/
│       └── a2_supplier/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── e2e/
│   └── security/
├── schemas/                 # Версионируемые JSON Schema / Proto
├── deploy/                  # Локальное и тестовое развёртывание
└── scripts/                 # Проверки, фикстуры и demo flow
```

На стадии MVP предпочтителен модульный монолит A3 с чёткими границами модулей. Выделение микросервисов выполняется после появления измеренной нагрузки или независимых циклов релиза.


## Как проверить

### 1. Автоматические тесты

```powershell
cd C:\Users\user\IdeaProjects\A2A
uv sync --dev
uv run pytest -q
uv run ruff check .
```

Ожидаемый результат: все тесты проходят, Ruff не находит ошибок.

### 2. Готовый demo-flow

```powershell
uv run a2a-demo
```

Demo выполняет полный локальный сценарий:

1. A1 создаёт потребность на 20 подшипников.
2. A3 параллельно получает три оферты от локальных demo-A2.
3. A3 проверяет ограничения и рассчитывает рейтинг.
4. Сделка переходит в `awaiting_approval`.
5. Demo имитирует подтверждение уполномоченным человеком.
6. Сделка проходит demo award, order confirmation, payment draft и fulfillment.
7. Финальный статус становится `completed`; создаются `order_id`,
   `payment_draft_id`, approval snapshot hash и mock-документы.

### 3. REST API и Swagger

Запустите сервер:

```powershell
uv run a2a-api
```

Проверьте:

- Swagger UI: `http://127.0.0.1:8000/docs`
- health: `http://127.0.0.1:8000/health`
- readiness: `http://127.0.0.1:8000/ready`
- Agent Card: `http://127.0.0.1:8000/.well-known/agent-card.json`

Health должен вернуть:

```json
{
  "status": "ok",
  "role": "A3",
  "llm_enabled": false,
  "llm_provider": "disabled"
}
```

### 4. Создание сделки через PowerShell

Не останавливая API, откройте второе окно PowerShell:

```powershell
$delivery = (Get-Date).AddDays(10).ToString("yyyy-MM-dd")
$expires = (Get-Date).ToUniversalTime().AddDays(1).ToString("o")

$body = @{
    intent = @{
        customer_id = "client-001"
        product = @{
            sku = "BEARING-6205-2RS"
            name = "Подшипник 6205-2RS"
            category = "mro.standardized"
            quantity = 20
        }
        delivery_city = "Москва"
        delivery_by = $delivery
        max_total = "25000.00"
        currency = "RUB"
    }
    mandate = @{
        customer_id = "client-001"
        authorized_by = "ivan.petrov"
        allowed_categories = @("mro.standardized")
        max_total = "25000.00"
        expires_at = $expires
    }
} | ConvertTo-Json -Depth 10

$deal = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/deals" `
    -ContentType "application/json" `
    -Body $body

$deal | ConvertTo-Json -Depth 20
```

Полезные поля:

```powershell
$deal.status
$deal.supplier_ids
$deal.comparison.explanation
$deal.comparison.recommended_quote_id
```

### 5. Подтверждение оферты

```powershell
$approval = @{
    quote_id = $deal.comparison.recommended_quote_id
    approved_by = "ivan.petrov"
    approval_snapshot_hash = $deal.approval_snapshot.snapshot_hash
} | ConvertTo-Json

$result = Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/deals/$($deal.deal_id)/approve" `
    -ContentType "application/json" `
    -Body $approval

$result | ConvertTo-Json
```

Ожидаемый статус: `completed`. Повторное подтверждение возвращает тот же
`order_id`, `payment_draft_id` и snapshot hash, не создавая второй заказ.

Evidence bundle доступен по:

```powershell
Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/api/v1/deals/$($deal.deal_id)/evidence" |
    ConvertTo-Json -Depth 30
```

В evidence входят `events` с trace/hash-полями и `outbox_messages` со статусами
публикации demo award/rejection/payment/document сообщений.

### 6. Проверка LLM provider

```powershell
Copy-Item .env.example .env
notepad .env
```

Для OpenRouter задайте:

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<ваш ключ>
OPENROUTER_MODEL=<выбранная модель OpenRouter>
```

Либо для GigaChat:

```dotenv
LLM_PROVIDER=gigachat
GIGACHAT_CREDENTIALS=<ключ авторизации>
GIGACHAT_MODEL=<доступная модель GigaChat>
GIGACHAT_SCOPE=<scope проекта>
```

Перезапустите API и вызовите в Swagger `POST /api/v1/intents/parse`:

```json
{
  "text": "Нужно купить 20 подшипников 6205-2RS с доставкой в Москву"
}
```

Без ключа endpoint вернёт HTTP `503`, но основной детерминированный procurement flow продолжит работать.

## React/TypeScript frontend

Frontend находится в каталоге `frontend/` и использует React 19, TypeScript и Vite.

Интерфейс показывает:

- схему взаимодействия `A1 → A3 → A2.1/A2.2/A2.3`;
- состояние API и LLM-провайдера;
- параметры мандата и закупочной потребности;
- все полученные оферты и причины отклонения;
- TCO, delivery, warranty, risk и итоговый score;
- рекомендацию A3 и версию ranking;
- подтверждение оферты человеком;
- `order_id` и `payment_draft_id`;
- approval snapshot hash;
- evidence/outbox tab;
- award/rejection, fulfillment и mock-документы;
- timeline событий Deal Ledger;
- frontend-события и ошибки запросов;
- полный raw JSON сделки.

### Development-режим

Первое окно PowerShell:

```powershell
cd C:\Users\user\IdeaProjects\A2A
uv run a2a-api
```

Второе окно:

```powershell
cd C:\Users\user\IdeaProjects\A2A\frontend
npm install
npm run dev
```

Откройте `http://127.0.0.1:5173`. Vite проксирует `/api`, `/health` и `/.well-known` на backend `http://127.0.0.1:8000`.

### Production-сборка

```powershell
cd C:\Users\user\IdeaProjects\A2A\frontend
npm install
npm run build

cd ..
uv run a2a-api
```

После сборки FastAPI отдаёт React frontend по адресу `http://127.0.0.1:8000/`.

Проверка frontend:

```powershell
npm --prefix frontend run lint
npm --prefix frontend run build
```
