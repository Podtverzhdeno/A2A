from dataclasses import dataclass

from sber_a2a.config import Settings, get_settings
from sber_a2a.integrations.contracts import OrderGateway, SupplierRiskGateway
from sber_a2a.integrations.mock import MockOrderGateway, MockSupplierRiskGateway
from sber_a2a.services.deals import DealService
from sber_a2a.services.llm import LanguageModelService
from sber_a2a.services.onboarding import AgentOnboardingService
from sber_a2a.services.store import SQLAlchemyDealStore
from sber_a2a.suppliers.mock import SupplierRegistry, build_demo_registry
from sber_a2a.suppliers.remote import RemoteSupplierAgent
from sber_a2a.workflow.graph import build_procurement_graph


@dataclass(frozen=True)
class Container:
    settings: Settings
    registry: SupplierRegistry
    llm: LanguageModelService
    deals: DealService
    store: SQLAlchemyDealStore
    order_gateway: OrderGateway
    risk_gateway: SupplierRiskGateway
    onboarding: AgentOnboardingService


def build_container(settings: Settings | None = None) -> Container:
    settings = settings or get_settings()
    if settings.supplier_mode == "remote":
        registry = SupplierRegistry(
            [
                RemoteSupplierAgent(
                    supplier_id,
                    endpoint,
                    timeout_seconds=settings.supplier_timeout_seconds,
                    max_attempts=settings.supplier_max_attempts,
                )
                for supplier_id, endpoint in settings.parsed_supplier_endpoints.items()
            ]
        )
    else:
        registry = build_demo_registry()
    llm = LanguageModelService(settings)
    store = SQLAlchemyDealStore(settings.database_url)
    risk_gateway = MockSupplierRiskGateway()
    graph = build_procurement_graph(
        registry,
        llm,
        risk_gateway,
        minimum_quotes=settings.minimum_quotes,
    )
    order_gateway = MockOrderGateway()
    onboarding = AgentOnboardingService(
        store,
        registry,
        timeout_seconds=settings.supplier_timeout_seconds,
        max_attempts=settings.supplier_max_attempts,
    )
    return Container(
        settings=settings,
        registry=registry,
        llm=llm,
        deals=DealService(graph, store, order_gateway),
        store=store,
        order_gateway=order_gateway,
        risk_gateway=risk_gateway,
        onboarding=onboarding,
    )
