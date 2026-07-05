export type DealStatus =
  | "draft"
  | "awaiting_approval"
  | "order_created"
  | "fulfilling"
  | "completed"
  | "failed";

export interface Health {
  status: string;
  role: string;
  llm_enabled: boolean;
  llm_provider: "disabled" | "openrouter" | "gigachat";
}

export interface SupplierSummary {
  supplier_id: string;
  name: string;
  categories: string[];
  active: boolean;
}

export interface Quote {
  quote_id: string;
  supplier_id: string;
  supplier_name: string;
  sku: string;
  product_name: string;
  quantity: number;
  unit_price: string;
  delivery_fee: string;
  currency: string;
  vat_rate: string;
  delivery_days: number;
  warranty_months: number;
  supplier_risk: string;
  payment_delay_days: number;
  valid_until: string;
}

export interface ComponentScores {
  price: string;
  delivery: string;
  warranty: string;
  risk: string;
  payment_terms: string;
}

export interface EvaluatedQuote {
  quote: Quote;
  eligible: boolean;
  rejection_reasons: string[];
  scores: ComponentScores | null;
  total_score: string | null;
}

export interface Comparison {
  evaluated_quotes: EvaluatedQuote[];
  recommended_quote_id: string | null;
  explanation: string;
  ranking_version: string;
}

export interface DealEvent {
  event_type: string;
  actor: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface ApprovalSnapshot {
  snapshot_id: string;
  quote_id: string;
  supplier_id: string;
  supplier_name: string;
  sku: string;
  product_name: string;
  quantity: number;
  total_cost: string;
  currency: string;
  delivery_days: number;
  warranty_months: number;
  payment_delay_days: number;
  ranking_version: string;
  total_score: string | null;
  snapshot_hash: string;
  created_at: string;
}

export interface OrderState {
  order_id: string;
  supplier_id: string;
  quote_id: string;
  status: "awarded" | "confirmed_by_supplier";
  confirmed_at: string | null;
}

export interface PaymentDraft {
  payment_draft_id: string;
  order_id: string;
  amount: string;
  currency: string;
  payee_supplier_id: string;
  status: "created" | "awaiting_customer_confirmation";
  created_at: string;
}

export interface FulfillmentUpdate {
  status:
    | "order_confirmed"
    | "packed"
    | "shipped"
    | "delivered"
    | "documents_ready"
    | "completed";
  actor: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface DocumentRef {
  document_id: string;
  document_type: string;
  title: string;
  source: string;
  sha256: string;
  created_at: string;
}

export interface Deal {
  deal_id: string;
  status: DealStatus;
  intent: {
    customer_id: string;
    product: {
      sku: string;
      name: string;
      category: string;
      quantity: number;
    };
    delivery_city: string;
    delivery_by: string;
    max_total: string | null;
    currency: string;
    weights: Record<string, string>;
  };
  mandate: {
    mandate_id: string;
    customer_id: string;
    authorized_by: string;
    allowed_categories: string[];
    max_total: string;
    expires_at: string;
    allowed_supplier_ids: string[] | null;
    requires_human_approval: boolean;
  };
  supplier_ids: string[];
  quotes: Quote[];
  comparison: Comparison | null;
  selected_quote_id: string | null;
  order_id: string | null;
  payment_draft_id: string | null;
  approval_snapshot: ApprovalSnapshot | null;
  order: OrderState | null;
  payment_draft: PaymentDraft | null;
  fulfillment: FulfillmentUpdate[];
  documents: DocumentRef[];
  errors: string[];
  events: DealEvent[];
  created_at: string;
  updated_at: string;
}

export interface DealInput {
  customerId: string;
  authorizedBy: string;
  sku: string;
  productName: string;
  quantity: number;
  deliveryCity: string;
  deliveryDays: number;
  maxTotal: number;
}

export interface ApprovalResult {
  deal_id: string;
  status: DealStatus;
  selected_quote_id: string;
  order_id: string;
  payment_draft_id: string;
  approval_snapshot_hash: string;
}

export interface OutboxMessage {
  outbox_id: string;
  aggregate_id: string;
  recipient_agent_id: string;
  message_type: string;
  idempotency_key: string;
  payload: Record<string, unknown>;
  status: "pending" | "published";
  attempts: number;
  correlation_id: string;
  causation_id: string | null;
  created_at: string;
  published_at: string | null;
}

export interface EvidenceBundle {
  deal: Deal;
  events: DealEvent[];
  approval_snapshot: ApprovalSnapshot | null;
  order: OrderState | null;
  payment_draft: PaymentDraft | null;
  fulfillment: FulfillmentUpdate[];
  documents: DocumentRef[];
  outbox_messages: OutboxMessage[];
}
