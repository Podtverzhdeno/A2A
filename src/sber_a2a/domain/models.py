import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


Money = Annotated[Decimal, Field(ge=Decimal("0"), decimal_places=2)]
Score = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("100"))]


class DealStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    ORDER_CREATED = "order_created"
    FULFILLING = "fulfilling"
    COMPLETED = "completed"
    FAILED = "failed"


class OrderStatus(StrEnum):
    AWARDED = "awarded"
    CONFIRMED_BY_SUPPLIER = "confirmed_by_supplier"


class PaymentDraftStatus(StrEnum):
    CREATED = "created"
    AWAITING_CUSTOMER_CONFIRMATION = "awaiting_customer_confirmation"


class FulfillmentStatus(StrEnum):
    ORDER_CONFIRMED = "order_confirmed"
    PACKED = "packed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    DOCUMENTS_READY = "documents_ready"
    COMPLETED = "completed"


class RankingWeights(BaseModel):
    price: Decimal = Decimal("0.40")
    delivery: Decimal = Decimal("0.25")
    warranty: Decimal = Decimal("0.15")
    risk: Decimal = Decimal("0.10")
    payment_terms: Decimal = Decimal("0.10")

    @model_validator(mode="after")
    def validate_sum(self) -> "RankingWeights":
        values = (
            self.price,
            self.delivery,
            self.warranty,
            self.risk,
            self.payment_terms,
        )
        if any(value < 0 for value in values):
            raise ValueError("Ranking weights cannot be negative")
        if abs(sum(values) - Decimal("1")) > Decimal("0.0001"):
            raise ValueError("Ranking weights must sum to 1")
        return self


class ProductRequest(BaseModel):
    sku: str = Field(min_length=2, max_length=100)
    name: str = Field(min_length=2, max_length=500)
    category: str = Field(default="mro.standardized", min_length=2)
    quantity: int = Field(gt=0, le=100_000)


class ProcurementIntent(BaseModel):
    customer_id: str = Field(min_length=2, max_length=100)
    product: ProductRequest
    delivery_city: str = Field(min_length=2, max_length=200)
    delivery_by: date
    max_total: Money | None = None
    currency: str = Field(default="RUB", pattern=r"^[A-Z]{3}$")
    weights: RankingWeights = Field(default_factory=RankingWeights)


class Mandate(BaseModel):
    mandate_id: UUID = Field(default_factory=uuid4)
    customer_id: str
    authorized_by: str = Field(min_length=2, max_length=100)
    allowed_categories: set[str] = Field(default_factory=lambda: {"mro.standardized"})
    max_total: Money
    expires_at: datetime
    allowed_supplier_ids: set[str] | None = None
    requires_human_approval: bool = True


class CreateDealRequest(BaseModel):
    intent: ProcurementIntent
    mandate: Mandate

    @model_validator(mode="after")
    def customer_matches(self) -> "CreateDealRequest":
        if self.intent.customer_id != self.mandate.customer_id:
            raise ValueError("Intent and mandate must belong to the same customer")
        return self


class SupplierSummary(BaseModel):
    supplier_id: str
    name: str
    categories: set[str]
    active: bool = True


class Quote(BaseModel):
    quote_id: UUID = Field(default_factory=uuid4)
    supplier_id: str
    supplier_name: str
    sku: str
    product_name: str
    quantity: int = Field(gt=0)
    unit_price: Money
    delivery_fee: Money = Decimal("0")
    currency: str = "RUB"
    vat_rate: Decimal = Decimal("0.20")
    delivery_days: int = Field(ge=0)
    warranty_months: int = Field(ge=0)
    supplier_risk: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    payment_delay_days: int = Field(ge=0)
    valid_until: datetime

    @property
    def goods_total(self) -> Decimal:
        return self.unit_price * self.quantity

    @property
    def total_cost(self) -> Decimal:
        return self.goods_total + self.delivery_fee


class ComponentScores(BaseModel):
    price: Score
    delivery: Score
    warranty: Score
    risk: Score
    payment_terms: Score


class EvaluatedQuote(BaseModel):
    quote: Quote
    eligible: bool
    rejection_reasons: list[str] = Field(default_factory=list)
    scores: ComponentScores | None = None
    total_score: Score | None = None


class Comparison(BaseModel):
    evaluated_quotes: list[EvaluatedQuote]
    recommended_quote_id: UUID | None
    explanation: str
    ranking_version: str = "deterministic-v1"


class DealEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: str
    actor: str
    details: dict[str, Any] = Field(default_factory=dict)
    correlation_id: UUID = Field(default_factory=uuid4)
    causation_id: UUID | None = None
    message_id: UUID = Field(default_factory=uuid4)
    payload_hash: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def set_payload_hash(self) -> "DealEvent":
        if self.payload_hash is None:
            payload = {
                "event_type": self.event_type,
                "actor": self.actor,
                "details": self.details,
            }
            encoded = json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
            self.payload_hash = hashlib.sha256(encoded).hexdigest()
        return self


class ApprovalSnapshot(BaseModel):
    snapshot_id: UUID = Field(default_factory=uuid4)
    quote_id: UUID
    supplier_id: str
    supplier_name: str
    sku: str
    product_name: str
    quantity: int
    total_cost: Money
    currency: str
    delivery_days: int
    warranty_months: int
    payment_delay_days: int
    ranking_version: str
    total_score: Score | None = None
    snapshot_hash: str
    created_at: datetime = Field(default_factory=utc_now)


class OrderState(BaseModel):
    order_id: UUID
    supplier_id: str
    quote_id: UUID
    status: OrderStatus
    confirmed_at: datetime | None = None


class PaymentDraft(BaseModel):
    payment_draft_id: UUID
    order_id: UUID
    amount: Money
    currency: str
    payee_supplier_id: str
    status: PaymentDraftStatus
    created_at: datetime = Field(default_factory=utc_now)


class FulfillmentUpdate(BaseModel):
    status: FulfillmentStatus
    actor: str = "A2:supplier"
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class DocumentRef(BaseModel):
    document_id: UUID = Field(default_factory=uuid4)
    document_type: str
    title: str
    source: str
    sha256: str
    created_at: datetime = Field(default_factory=utc_now)


class DealRecord(BaseModel):
    deal_id: UUID
    status: DealStatus
    intent: ProcurementIntent
    mandate: Mandate
    supplier_ids: list[str] = Field(default_factory=list)
    quotes: list[Quote] = Field(default_factory=list)
    comparison: Comparison | None = None
    selected_quote_id: UUID | None = None
    order_id: UUID | None = None
    payment_draft_id: UUID | None = None
    approval_snapshot: ApprovalSnapshot | None = None
    order: OrderState | None = None
    payment_draft: PaymentDraft | None = None
    fulfillment: list[FulfillmentUpdate] = Field(default_factory=list)
    documents: list[DocumentRef] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    events: list[DealEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ApprovalRequest(BaseModel):
    quote_id: UUID
    approved_by: str = Field(min_length=2, max_length=100)
    approval_snapshot_hash: str = Field(min_length=64, max_length=64)


class ApprovalResult(BaseModel):
    deal_id: UUID
    status: DealStatus
    selected_quote_id: UUID
    order_id: UUID
    payment_draft_id: UUID
    approval_snapshot_hash: str


class EvidenceBundle(BaseModel):
    deal: DealRecord
    events: list[DealEvent]
    approval_snapshot: ApprovalSnapshot | None
    order: OrderState | None
    payment_draft: PaymentDraft | None
    fulfillment: list[FulfillmentUpdate]
    documents: list[DocumentRef]
    outbox_messages: list["OutboxMessage"] = Field(default_factory=list)


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"


class OutboxMessage(BaseModel):
    outbox_id: UUID = Field(default_factory=uuid4)
    aggregate_id: UUID
    recipient_agent_id: str
    message_type: str
    idempotency_key: str
    payload: dict[str, Any]
    status: OutboxStatus = OutboxStatus.PENDING
    attempts: int = 0
    correlation_id: UUID
    causation_id: UUID | None = None
    created_at: datetime = Field(default_factory=utc_now)
    published_at: datetime | None = None


class ParseIntentRequest(BaseModel):
    text: str = Field(min_length=10, max_length=10_000)


class ParsedIntentDraft(BaseModel):
    sku: str | None = None
    product_name: str
    category: str = "mro.standardized"
    quantity: int = Field(gt=0)
    delivery_city: str | None = None
    delivery_by: date | None = None
    max_total: Decimal | None = Field(default=None, ge=0)


class OrganizationStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    SUSPENDED = "suspended"


class AgentRegistrationStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class UpdateAgentStatusRequest(BaseModel):
    status: AgentRegistrationStatus


class AgentHostingMode(StrEnum):
    MANAGED = "managed"
    EXTERNAL = "external"


class CreateOrganizationRequest(BaseModel):
    legal_name: str = Field(min_length=2, max_length=300)
    tax_id: str = Field(min_length=5, max_length=30)
    roles: set[str] = Field(default_factory=lambda: {"supplier"})


class Organization(BaseModel):
    organization_id: UUID = Field(default_factory=uuid4)
    legal_name: str
    tax_id: str
    roles: set[str]
    status: OrganizationStatus = OrganizationStatus.VERIFIED
    created_at: datetime = Field(default_factory=utc_now)


class RegisterSupplierAgentRequest(BaseModel):
    organization_id: UUID
    agent_id: str = Field(min_length=2, max_length=100)
    endpoint_url: str = Field(pattern=r"^https?://")
    categories: set[str] = Field(default_factory=lambda: {"mro.standardized"})
    hosting_mode: AgentHostingMode = AgentHostingMode.EXTERNAL


class AgentRegistration(BaseModel):
    registration_id: UUID = Field(default_factory=uuid4)
    organization_id: UUID
    agent_id: str
    role: str = "A2"
    endpoint_url: str
    categories: set[str]
    hosting_mode: AgentHostingMode
    status: AgentRegistrationStatus
    agent_card_snapshot: dict
    last_checked_at: datetime
    created_at: datetime = Field(default_factory=utc_now)
