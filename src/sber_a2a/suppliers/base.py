from typing import Protocol

from sber_a2a.domain.models import ProcurementIntent, Quote, SupplierSummary


class SupplierAgent(Protocol):
    @property
    def summary(self) -> SupplierSummary: ...

    async def create_quote(self, intent: ProcurementIntent) -> Quote | None: ...
