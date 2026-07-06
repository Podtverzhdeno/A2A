import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sber_a2a.domain.models import ProcurementIntent, Quote, SupplierSummary
from sber_a2a.suppliers.base import SupplierAgent


@dataclass(frozen=True)
class CatalogItem:
    sku: str
    name: str
    unit_price: Decimal
    delivery_fee: Decimal
    delivery_days: int
    warranty_months: int
    supplier_risk: Decimal
    payment_delay_days: int


class MockSupplierAgent:
    def __init__(
        self,
        supplier_id: str,
        name: str,
        catalog: dict[str, CatalogItem],
        *,
        categories: set[str] | None = None,
    ) -> None:
        self._summary = SupplierSummary(
            supplier_id=supplier_id,
            name=name,
            categories=categories or {"mro.standardized"},
        )
        self._catalog = catalog

    @property
    def summary(self) -> SupplierSummary:
        return self._summary

    async def create_quote(self, intent: ProcurementIntent) -> Quote | None:
        item = self._catalog.get(intent.product.sku)
        if item is None:
            return None
        return Quote(
            supplier_id=self.summary.supplier_id,
            supplier_name=self.summary.name,
            sku=item.sku,
            product_name=item.name,
            quantity=intent.product.quantity,
            unit_price=item.unit_price,
            delivery_fee=item.delivery_fee,
            delivery_days=item.delivery_days,
            warranty_months=item.warranty_months,
            supplier_risk=item.supplier_risk,
            payment_delay_days=item.payment_delay_days,
            valid_until=datetime.now(UTC) + timedelta(minutes=30),
        )


class SupplierRegistry:
    def __init__(self, agents: list[SupplierAgent]) -> None:
        self._agents = {
            agent.summary.supplier_id: agent
            for agent in agents
            if agent.summary.active
        }

    def list_suppliers(self) -> list[SupplierSummary]:
        return [agent.summary for agent in self._agents.values()]

    def discover(
        self,
        category: str,
        allowed_supplier_ids: set[str] | None = None,
    ) -> list[SupplierAgent]:
        return [
            agent
            for supplier_id, agent in self._agents.items()
            if category in agent.summary.categories
            and (allowed_supplier_ids is None or supplier_id in allowed_supplier_ids)
        ]

    def get(self, supplier_id: str) -> SupplierAgent | None:
        return self._agents.get(supplier_id)

    def register(self, agent: SupplierAgent) -> None:
        if not agent.summary.active:
            raise ValueError("Cannot register an inactive supplier agent")
        self._agents[agent.summary.supplier_id] = agent

    def unregister(self, supplier_id: str) -> None:
        self._agents.pop(supplier_id, None)


def _catalog(
    *,
    bearing_price: str,
    delivery_fee: str,
    delivery_days: int,
    warranty_months: int,
    risk: str,
    payment_delay_days: int,
) -> dict[str, CatalogItem]:
    return {
        "BEARING-6205-2RS": CatalogItem(
            sku="BEARING-6205-2RS",
            name="Подшипник 6205-2RS",
            unit_price=Decimal(bearing_price),
            delivery_fee=Decimal(delivery_fee),
            delivery_days=delivery_days,
            warranty_months=warranty_months,
            supplier_risk=Decimal(risk),
            payment_delay_days=payment_delay_days,
        )
    }


def build_demo_agents() -> list[MockSupplierAgent]:
    return [
            MockSupplierAgent(
                "supplier-a",
                "ПромКомплект",
                _catalog(
                    bearing_price="850.00",
                    delivery_fee="1500.00",
                    delivery_days=3,
                    warranty_months=12,
                    risk="0.08",
                    payment_delay_days=10,
                ),
            ),
            MockSupplierAgent(
                "supplier-b",
                "Индустрия-Снаб",
                _catalog(
                    bearing_price="790.00",
                    delivery_fee="2500.00",
                    delivery_days=8,
                    warranty_months=12,
                    risk="0.15",
                    payment_delay_days=30,
                ),
            ),
            MockSupplierAgent(
                "supplier-c",
                "ТехРесурс",
                _catalog(
                    bearing_price="930.00",
                    delivery_fee="0.00",
                    delivery_days=2,
                    warranty_months=24,
                    risk="0.04",
                    payment_delay_days=15,
                ),
            ),
        ]


def build_demo_registry() -> SupplierRegistry:
    return SupplierRegistry(build_demo_agents())


def load_catalog_supplier(
    supplier_id: str,
    catalog_file: str | Path,
) -> MockSupplierAgent:
    payload = json.loads(Path(catalog_file).read_text(encoding="utf-8"))
    categories = set(payload.get("categories") or {"mro.standardized"})
    catalog = {
        item["sku"]: CatalogItem(
            sku=item["sku"],
            name=item["name"],
            unit_price=Decimal(str(item["unit_price"])),
            delivery_fee=Decimal(str(item.get("delivery_fee", "0.00"))),
            delivery_days=int(item["delivery_days"]),
            warranty_months=int(item["warranty_months"]),
            supplier_risk=Decimal(str(item.get("supplier_risk", "0.50"))),
            payment_delay_days=int(item.get("payment_delay_days", 0)),
        )
        for item in payload["items"]
    }
    return MockSupplierAgent(
        supplier_id,
        payload.get("name", supplier_id),
        catalog,
        categories=categories,
    )


def get_demo_agent(supplier_id: str) -> MockSupplierAgent:
    for agent in build_demo_agents():
        if agent.summary.supplier_id == supplier_id:
            return agent
    raise ValueError(f"Unknown demo supplier: {supplier_id}")
