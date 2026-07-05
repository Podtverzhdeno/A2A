import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState
} from "react";
import { api } from "./api";
import type {
  Deal,
  DealEvent,
  DealInput,
  EvaluatedQuote,
  Health,
  SupplierSummary
} from "./types";

const INITIAL_INPUT: DealInput = {
  customerId: "client-001",
  authorizedBy: "ivan.petrov",
  sku: "BEARING-6205-2RS",
  productName: "Подшипник 6205-2RS",
  quantity: 20,
  deliveryCity: "Москва",
  deliveryDays: 10,
  maxTotal: 25_000
};

const EVENT_LABELS: Record<string, string> = {
  deal_created: "Сделка создана",
  mandate_validated: "Мандат проверен",
  suppliers_discovered: "Поставщики обнаружены",
  rfq_sent: "RFQ отправлен поставщику",
  quote_received: "Оферта получена от A2",
  quotes_collected: "Оферты получены",
  quotes_ranked: "Оферты ранжированы",
  comparison_explained: "Объяснение сформировано",
  workflow_completed: "Workflow завершён",
  supplier_request_failed: "Поставщик не ответил",
  workflow_failed: "Workflow завершился с ошибкой",
  quote_approved: "Оферта подтверждена",
  order_created: "Заказ создан"
};

const STATUS_LABELS = {
  draft: "Черновик",
  awaiting_approval: "Ожидает подтверждения",
  order_created: "Заказ создан",
  failed: "Ошибка"
} as const;

interface ClientLog {
  id: number;
  level: "info" | "success" | "error";
  message: string;
  timestamp: Date;
}

function formatMoney(value: string | number, currency = "RUB"): string {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency,
    maximumFractionDigits: 2
  }).format(Number(value));
}

function formatTime(value: string | Date): string {
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    fractionalSecondDigits: 3
  }).format(new Date(value));
}

function shortId(value: string | null | undefined): string {
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [suppliers, setSuppliers] = useState<SupplierSummary[]>([]);
  const [history, setHistory] = useState<Deal[]>([]);
  const [deal, setDeal] = useState<Deal | null>(null);
  const [input, setInput] = useState<DealInput>(INITIAL_INPUT);
  const [selectedQuote, setSelectedQuote] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"ledger" | "json">("ledger");
  const [clientLogs, setClientLogs] = useState<ClientLog[]>([]);
  const eventSourceRef = useRef<EventSource | null>(null);

  const addClientLog = useCallback(
    (level: ClientLog["level"], message: string) => {
      setClientLogs((current) => [
        ...current,
        {
          id: Date.now() + Math.random(),
          level,
          message,
          timestamp: new Date()
        }
      ]);
    },
    []
  );

  const loadSystem = useCallback(async () => {
    try {
      const [healthResult, supplierResult, dealsResult] = await Promise.all([
        api.health(),
        api.suppliers(),
        api.deals()
      ]);
      setHealth(healthResult);
      setSuppliers(supplierResult);
      setHistory(dealsResult);
    } catch (reason) {
      setHealth(null);
      setError(reason instanceof Error ? reason.message : "Backend недоступен");
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(loadSystem);
    return () => eventSourceRef.current?.close();
  }, [loadSystem]);

  const observeDeal = useCallback(
    (dealId: string) => {
      eventSourceRef.current?.close();
      const source = new EventSource(
        `/api/v1/deals/${dealId}/events/stream`
      );
      eventSourceRef.current = source;
      source.addEventListener("deal_event", (event) => {
        const payload = JSON.parse((event as MessageEvent).data) as DealEvent;
        addClientLog(
          payload.event_type === "supplier_request_failed" ? "error" : "info",
          EVENT_LABELS[payload.event_type] ?? payload.event_type
        );
        void api.getDeal(dealId).then((current) => {
          setDeal(current);
          setHistory((items) => [
            current,
            ...items.filter((item) => item.deal_id !== current.deal_id)
          ]);
          if (current.comparison?.recommended_quote_id) {
            setSelectedQuote(current.comparison.recommended_quote_id);
          }
        });
      });
      source.addEventListener("stream_complete", () => {
        source.close();
        void api.getDeal(dealId).then((current) => {
          setDeal(current);
          setHistory((items) => [
            current,
            ...items.filter((item) => item.deal_id !== current.deal_id)
          ]);
          setSelectedQuote(
            current.comparison?.recommended_quote_id ?? null
          );
          addClientLog(
            current.status === "failed" ? "error" : "success",
            current.status === "failed"
              ? "A3 не смог завершить закупочный workflow"
              : `A3 завершил RFQ: получено ${current.quotes.length} оферт`
          );
        });
      });
      source.onerror = () => {
        source.close();
      };
    },
    [addClientLog]
  );

  useEffect(() => {
    const dealId = new URLSearchParams(window.location.search).get("deal");
    if (!dealId) return;
    void api.getDeal(dealId).then((current) => {
      setDeal(current);
      setSelectedQuote(current.comparison?.recommended_quote_id ?? null);
      if (current.status === "draft") {
        observeDeal(current.deal_id);
      }
    });
  }, [observeDeal]);


  const createDeal = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setClientLogs([]);
    addClientLog("info", "A1 отправляет ProcurementIntent агенту A3");
    try {
      const result = await api.createDeal(input);
      setDeal(result);
      window.history.replaceState(null, "", `/?deal=${result.deal_id}`);
      setHistory((items) => [
        result,
        ...items.filter((item) => item.deal_id !== result.deal_id)
      ]);
      setSelectedQuote(null);
      addClientLog("success", `Сделка ${shortId(result.deal_id)} принята A3`);
      observeDeal(result.deal_id);
    } catch (reason) {
      const message =
        reason instanceof Error ? reason.message : "Не удалось создать сделку";
      setError(message);
      addClientLog("error", message);
    } finally {
      setLoading(false);
    }
  };

  const refreshDeal = async () => {
    if (!deal) return;
    try {
      const result = await api.getDeal(deal.deal_id);
      setDeal(result);
      addClientLog("info", "Состояние сделки обновлено из Deal Ledger");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Ошибка обновления");
    }
  };

  const approveQuote = async () => {
    if (!deal || !selectedQuote) return;
    setLoading(true);
    setError(null);
    addClientLog("info", `Подтверждение оферты ${shortId(selectedQuote)}`);
    try {
      const result = await api.approve(
        deal.deal_id,
        selectedQuote,
        deal.mandate.authorized_by
      );
      addClientLog(
        "success",
        `Создан заказ ${shortId(result.order_id)} и платёжный черновик`
      );
      const refreshed = await api.getDeal(deal.deal_id);
      setDeal(refreshed);
    } catch (reason) {
      const message =
        reason instanceof Error ? reason.message : "Подтверждение не выполнено";
      setError(message);
      addClientLog("error", message);
    } finally {
      setLoading(false);
    }
  };

  const selectedEvaluation = useMemo(
    () =>
      deal?.comparison?.evaluated_quotes.find(
        (item) => item.quote.quote_id === selectedQuote
      ) ?? null,
    [deal, selectedQuote]
  );

  return (
    <div className="app-shell">
      <Header health={health} onRefresh={loadSystem} />

      <main className="workspace">
        <aside className="control-panel">
          <section className="panel-heading">
            <div>
              <p className="eyebrow">Новая закупка</p>
              <h2>Параметры A1</h2>
            </div>
            <span className="role-badge role-a1">A1</span>
          </section>

          <DealForm
            input={input}
            loading={loading}
            onChange={setInput}
            onSubmit={createDeal}
          />

          {deal && (
            <section className="current-deal">
              <div className="section-title-row">
                <h3>Текущая сделка</h3>
                <button className="icon-button" onClick={refreshDeal} title="Обновить">
                  ↻
                </button>
              </div>
              <dl>
                <div>
                  <dt>Deal ID</dt>
                  <dd title={deal.deal_id}>{shortId(deal.deal_id)}</dd>
                </div>
                <div>
                  <dt>Мандат</dt>
                  <dd title={deal.mandate.mandate_id}>
                    {shortId(deal.mandate.mandate_id)}
                  </dd>
                </div>
                <div>
                  <dt>Статус</dt>
                  <dd>
                    <StatusBadge status={deal.status} />
                  </dd>
                </div>
              </dl>
            </section>
          )}

          <section className="deal-history">
            <div className="section-title-row">
              <h3>История сделок</h3>
              <span>{history.length}</span>
            </div>
            {history.length === 0 ? (
              <p className="history-empty">Сделок пока нет</p>
            ) : (
              <div className="history-list">
                {history.map((item) => (
                  <button
                    className={
                      item.deal_id === deal?.deal_id ? "active" : ""
                    }
                    key={item.deal_id}
                    onClick={() => {
                      setDeal(item);
                      setSelectedQuote(
                        item.comparison?.recommended_quote_id ?? null
                      );
                      window.history.replaceState(
                        null,
                        "",
                        `/?deal=${item.deal_id}`
                      );
                      if (item.status === "draft") {
                        observeDeal(item.deal_id);
                      }
                    }}
                  >
                    <span>{item.intent.product.sku}</span>
                    <small>{shortId(item.deal_id)}</small>
                    <StatusBadge status={item.status} />
                  </button>
                ))}
              </div>
            )}
          </section>
        </aside>

        <section className="main-stage">
          {error && (
            <div className="error-banner">
              <span>!</span>
              <p>{error}</p>
              <button onClick={() => setError(null)}>×</button>
            </div>
          )}

          <AgentFlow
            suppliers={suppliers}
            deal={deal}
            loading={loading}
          />

          {!deal ? (
            <EmptyState />
          ) : (
            <>
              <DealOverview deal={deal} />
              <QuoteComparison
                deal={deal}
                selectedQuote={selectedQuote}
                onSelect={setSelectedQuote}
              />

              <div className="decision-panel">
                <div>
                  <p className="eyebrow">Human-in-the-loop</p>
                  <h3>Подтверждение существенных условий</h3>
                  <p>
                    A3 не создаст заказ без явного решения пользователя,
                    указанного в мандате.
                  </p>
                </div>
                <div className="decision-summary">
                  <span>Выбрано</span>
                  <strong>
                    {selectedEvaluation?.quote.supplier_name ?? "Нет оферты"}
                  </strong>
                  <small>
                    {selectedEvaluation
                      ? formatMoney(
                          Number(selectedEvaluation.quote.unit_price) *
                            selectedEvaluation.quote.quantity +
                            Number(selectedEvaluation.quote.delivery_fee)
                        )
                      : "—"}
                  </small>
                </div>
                <button
                  className="primary-button approve-button"
                  disabled={
                    loading ||
                    deal.status !== "awaiting_approval" ||
                    !selectedEvaluation?.eligible
                  }
                  onClick={approveQuote}
                >
                  {deal.status === "order_created"
                    ? "Заказ уже создан"
                    : "Подтвердить и создать заказ"}
                </button>
              </div>

              {deal.status === "order_created" && (
                <OrderResult deal={deal} />
              )}
            </>
          )}
        </section>

        <aside className="observability-panel">
          <div className="tabs">
            <button
              className={activeTab === "ledger" ? "active" : ""}
              onClick={() => setActiveTab("ledger")}
            >
              Deal Ledger
            </button>
            <button
              className={activeTab === "json" ? "active" : ""}
              onClick={() => setActiveTab("json")}
            >
              Raw JSON
            </button>
          </div>

          {activeTab === "ledger" ? (
            <EventLedger
              events={deal?.events ?? []}
              clientLogs={clientLogs}
              loading={loading}
            />
          ) : (
            <pre className="raw-json">
              {deal
                ? JSON.stringify(deal, null, 2)
                : "// Создайте сделку, чтобы увидеть state A3"}
            </pre>
          )}
        </aside>
      </main>
    </div>
  );
}

function Header({
  health,
  onRefresh
}: {
  health: Health | null;
  onRefresh: () => Promise<void>;
}) {
  return (
    <header className="topbar">
      <div className="brand">
        <div className="brand-mark">A3</div>
        <div>
          <h1>A2A Control Room</h1>
          <p>Sber Procurement Orchestrator</p>
        </div>
      </div>
      <div className="topbar-status">
        <button className="system-chip" onClick={() => void onRefresh()}>
          <span className={`status-dot ${health ? "online" : "offline"}`} />
          API {health ? "online" : "offline"}
        </button>
        <div className="system-chip">
          <span className={`status-dot ${health?.llm_enabled ? "llm" : "muted"}`} />
          LLM {health?.llm_enabled ? health.llm_provider : "disabled"}
        </div>
        <a className="docs-link" href="/docs" target="_blank" rel="noreferrer">
          API docs ↗
        </a>
      </div>
    </header>
  );
}

function DealForm({
  input,
  loading,
  onChange,
  onSubmit
}: {
  input: DealInput;
  loading: boolean;
  onChange: (value: DealInput) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  const update = <K extends keyof DealInput>(key: K, value: DealInput[K]) =>
    onChange({ ...input, [key]: value });

  return (
    <form className="deal-form" onSubmit={onSubmit}>
      <label>
        Клиент
        <input
          value={input.customerId}
          onChange={(event) => update("customerId", event.target.value)}
          required
        />
      </label>
      <label>
        Уполномоченный
        <input
          value={input.authorizedBy}
          onChange={(event) => update("authorizedBy", event.target.value)}
          required
        />
      </label>
      <div className="form-divider" />
      <label>
        SKU
        <input
          value={input.sku}
          onChange={(event) => update("sku", event.target.value)}
          required
        />
      </label>
      <label>
        Наименование
        <input
          value={input.productName}
          onChange={(event) => update("productName", event.target.value)}
          required
        />
      </label>
      <div className="form-grid">
        <label>
          Количество
          <input
            type="number"
            min="1"
            value={input.quantity}
            onChange={(event) => update("quantity", Number(event.target.value))}
            required
          />
        </label>
        <label>
          Срок, дней
          <input
            type="number"
            min="1"
            value={input.deliveryDays}
            onChange={(event) =>
              update("deliveryDays", Number(event.target.value))
            }
            required
          />
        </label>
      </div>
      <label>
        Город доставки
        <input
          value={input.deliveryCity}
          onChange={(event) => update("deliveryCity", event.target.value)}
          required
        />
      </label>
      <label>
        Лимит сделки, ₽
        <input
          type="number"
          min="1"
          step="0.01"
          value={input.maxTotal}
          onChange={(event) => update("maxTotal", Number(event.target.value))}
          required
        />
      </label>
      <button className="primary-button" disabled={loading}>
        {loading ? (
          <>
            <span className="spinner" /> A3 выполняет workflow
          </>
        ) : (
          "Запросить предложения"
        )}
      </button>
    </form>
  );
}

function AgentFlow({
  suppliers,
  deal,
  loading
}: {
  suppliers: SupplierSummary[];
  deal: Deal | null;
  loading: boolean;
}) {
  const activeSuppliers = new Set(deal?.supplier_ids ?? []);
  return (
    <section className="agent-flow-card">
      <div className="agent-node client-node">
        <div className="node-icon">A1</div>
        <div>
          <strong>Агент клиента</strong>
          <span>{deal?.intent.customer_id ?? "Ожидает intent"}</span>
        </div>
      </div>
      <FlowConnector active={Boolean(deal) || loading} label="Intent + мандат" />
      <div className={`agent-node sber-node ${loading ? "processing" : ""}`}>
        <div className="node-icon">A3</div>
        <div>
          <strong>Агент Сбера</strong>
          <span>Trust · Policy · Ranking</span>
        </div>
        {loading && <span className="node-pulse" />}
      </div>
      <FlowConnector
        active={Boolean(deal?.supplier_ids.length) || loading}
        label="Parallel RFQ"
      />
      <div className="supplier-cluster">
        {suppliers.map((supplier, index) => (
          <div
            className={`supplier-node ${
              activeSuppliers.has(supplier.supplier_id) ? "active" : ""
            }`}
            key={supplier.supplier_id}
          >
            <span>A2.{index + 1}</span>
            <div>
              <strong>{supplier.name}</strong>
              <small>{supplier.active ? "Аккредитован" : "Отключён"}</small>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function FlowConnector({
  active,
  label
}: {
  active: boolean;
  label: string;
}) {
  return (
    <div className={`flow-connector ${active ? "active" : ""}`}>
      <span>{label}</span>
      <div className="flow-line">
        <i />
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <section className="empty-state">
      <div className="empty-illustration">
        <span>A1</span>
        <i />
        <span className="center">A3</span>
        <i />
        <span>A2</span>
      </div>
      <p className="eyebrow">Система готова</p>
      <h2>Создайте закупочную потребность</h2>
      <p>
        A3 проверит мандат, параллельно обратится к поставщикам и покажет
        воспроизводимое сравнение оферт.
      </p>
    </section>
  );
}

function DealOverview({ deal }: { deal: Deal }) {
  const eligible =
    deal.comparison?.evaluated_quotes.filter((item) => item.eligible).length ?? 0;
  return (
    <section className="metrics-grid">
      <Metric
        label="Получено оферт"
        value={String(deal.quotes.length)}
        hint={`из ${deal.supplier_ids.length} запросов`}
      />
      <Metric
        label="Прошли ограничения"
        value={String(eligible)}
        hint="hard constraints"
      />
      <Metric
        label="Лимит мандата"
        value={formatMoney(deal.mandate.max_total)}
        hint={`до ${new Date(deal.mandate.expires_at).toLocaleDateString("ru-RU")}`}
      />
      <Metric
        label="Событий в Ledger"
        value={String(deal.events.length)}
        hint="полный audit trail"
      />
    </section>
  );
}

function Metric({
  label,
  value,
  hint
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <article className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{hint}</small>
    </article>
  );
}

function QuoteComparison({
  deal,
  selectedQuote,
  onSelect
}: {
  deal: Deal;
  selectedQuote: string | null;
  onSelect: (id: string) => void;
}) {
  const items = deal.comparison?.evaluated_quotes ?? [];
  return (
    <section className="quote-section">
      <div className="section-title-row">
        <div>
          <p className="eyebrow">Decision support</p>
          <h2>Сравнение оферт</h2>
        </div>
        <span className="ranking-version">
          {deal.comparison?.ranking_version ?? "—"}
        </span>
      </div>

      {deal.comparison && (
        <div className="explanation">
          <span>i</span>
          <p>{deal.comparison.explanation}</p>
        </div>
      )}

      <div className="quote-grid">
        {items.map((item, index) => (
          <QuoteCard
            key={item.quote.quote_id}
            item={item}
            rank={index + 1}
            recommended={
              item.quote.quote_id === deal.comparison?.recommended_quote_id
            }
            selected={item.quote.quote_id === selectedQuote}
            disabled={deal.status !== "awaiting_approval"}
            onSelect={() => onSelect(item.quote.quote_id)}
          />
        ))}
      </div>
    </section>
  );
}

function QuoteCard({
  item,
  rank,
  recommended,
  selected,
  disabled,
  onSelect
}: {
  item: EvaluatedQuote;
  rank: number;
  recommended: boolean;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
}) {
  const total =
    Number(item.quote.unit_price) * item.quote.quantity +
    Number(item.quote.delivery_fee);
  const score = Number(item.total_score ?? 0);
  return (
    <button
      className={`quote-card ${selected ? "selected" : ""} ${
        !item.eligible ? "ineligible" : ""
      }`}
      disabled={!item.eligible || disabled}
      onClick={onSelect}
    >
      <div className="quote-card-head">
        <span className="rank">#{rank}</span>
        {recommended && <span className="recommended">Рекомендация A3</span>}
        {!item.eligible && <span className="rejected">Отклонено</span>}
      </div>
      <h3>{item.quote.supplier_name}</h3>
      <p className="supplier-id">{item.quote.supplier_id}</p>
      <strong className="quote-price">{formatMoney(total)}</strong>
      <small>
        {formatMoney(item.quote.unit_price)} × {item.quote.quantity} + доставка
      </small>

      <div className="quote-details">
        <div>
          <span>Поставка</span>
          <strong>{item.quote.delivery_days} дн.</strong>
        </div>
        <div>
          <span>Гарантия</span>
          <strong>{item.quote.warranty_months} мес.</strong>
        </div>
        <div>
          <span>Отсрочка</span>
          <strong>{item.quote.payment_delay_days} дн.</strong>
        </div>
      </div>

      {item.eligible ? (
        <div className="score-block">
          <div>
            <span>Итоговый score</span>
            <strong>{item.total_score}</strong>
          </div>
          <div className="score-track">
            <i style={{ width: `${score}%` }} />
          </div>
        </div>
      ) : (
        <ul className="rejection-list">
          {item.rejection_reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </button>
  );
}

function EventLedger({
  events,
  clientLogs,
  loading
}: {
  events: DealEvent[];
  clientLogs: ClientLog[];
  loading: boolean;
}) {
  return (
    <div className="ledger">
      <div className="ledger-header">
        <div>
          <p className="eyebrow">Observability</p>
          <h2>Журнал действий</h2>
        </div>
        <span>{events.length + clientLogs.length}</span>
      </div>

      {events.length === 0 && clientLogs.length === 0 && (
        <div className="empty-logs">
          <span>_</span>
          <p>События появятся после запуска workflow</p>
        </div>
      )}

      <div className="timeline">
        {clientLogs.map((log) => (
          <article className={`timeline-item client ${log.level}`} key={log.id}>
            <div className="timeline-marker" />
            <div className="timeline-content">
              <time>{formatTime(log.timestamp)}</time>
              <strong>Frontend</strong>
              <p>{log.message}</p>
            </div>
          </article>
        ))}

        {events.map((event, index) => (
          <article className="timeline-item" key={`${event.created_at}-${index}`}>
            <div className="timeline-marker" />
            <div className="timeline-content">
              <time>{formatTime(event.created_at)}</time>
              <div className="event-title">
                <strong>{EVENT_LABELS[event.event_type] ?? event.event_type}</strong>
                <span>{event.actor}</span>
              </div>
              <code>{JSON.stringify(event.details)}</code>
            </div>
          </article>
        ))}

        {loading && (
          <article className="timeline-item pending">
            <div className="timeline-marker" />
            <div className="timeline-content">
              <strong>A3 выполняет следующий шаг…</strong>
            </div>
          </article>
        )}
      </div>
    </div>
  );
}

function OrderResult({ deal }: { deal: Deal }) {
  return (
    <section className="order-result">
      <div className="success-icon">✓</div>
      <div>
        <p className="eyebrow">Transaction result</p>
        <h2>Заказ успешно создан</h2>
        <p>
          Платёж не выполнен автоматически — сформирован только черновик для
          штатного подтверждения.
        </p>
      </div>
      <dl>
        <div>
          <dt>Order ID</dt>
          <dd title={deal.order_id ?? ""}>{shortId(deal.order_id)}</dd>
        </div>
        <div>
          <dt>Payment draft</dt>
          <dd title={deal.payment_draft_id ?? ""}>
            {shortId(deal.payment_draft_id)}
          </dd>
        </div>
      </dl>
    </section>
  );
}

function StatusBadge({ status }: { status: Deal["status"] }) {
  return (
    <span className={`deal-status status-${status}`}>
      {STATUS_LABELS[status]}
    </span>
  );
}

export default App;
