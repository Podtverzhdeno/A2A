from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from sber_a2a.config import Settings
from sber_a2a.container import Container, build_container
from sber_a2a.domain.models import (
    CreateDealRequest,
    Mandate,
    ProcurementIntent,
    ProductRequest,
)


@pytest.fixture
def container() -> Container:
    return build_container(
        Settings(
            llm_provider="disabled",
            database_url="sqlite+aiosqlite:///:memory:",
            _env_file=None,
        )
    )


@pytest.fixture
def deal_request() -> CreateDealRequest:
    return CreateDealRequest(
        intent=ProcurementIntent(
            customer_id="customer-1",
            product=ProductRequest(
                sku="BEARING-6205-2RS",
                name="Подшипник 6205-2RS",
                quantity=20,
            ),
            delivery_city="Москва",
            delivery_by=date.today() + timedelta(days=10),
            max_total=Decimal("25000.00"),
        ),
        mandate=Mandate(
            customer_id="customer-1",
            authorized_by="approver-1",
            max_total=Decimal("25000.00"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        ),
    )
