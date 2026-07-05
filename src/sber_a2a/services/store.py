import asyncio
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from sber_a2a.domain.models import AgentRegistration, DealRecord, Organization


class DealNotFoundError(KeyError):
    pass


class DealStore(Protocol):
    async def put(self, deal: DealRecord) -> None: ...

    async def get(self, deal_id: UUID) -> DealRecord: ...

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[DealRecord]: ...


class InMemoryDealStore:
    def __init__(self) -> None:
        self._deals: dict[UUID, DealRecord] = {}
        self._lock = asyncio.Lock()

    async def put(self, deal: DealRecord) -> None:
        async with self._lock:
            self._deals[deal.deal_id] = deal.model_copy(deep=True)

    async def get(self, deal_id: UUID) -> DealRecord:
        async with self._lock:
            deal = self._deals.get(deal_id)
            if deal is None:
                raise DealNotFoundError(str(deal_id))
            return deal.model_copy(deep=True)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[DealRecord]:
        async with self._lock:
            items = sorted(
                self._deals.values(),
                key=lambda deal: deal.updated_at,
                reverse=True,
            )
            if status is not None:
                items = [deal for deal in items if deal.status.value == status]
            return [
                deal.model_copy(deep=True)
                for deal in items[offset : offset + limit]
            ]


class Base(DeclarativeBase):
    pass


class DealRow(Base):
    __tablename__ = "deals"

    deal_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    customer_id: Mapped[str] = mapped_column(String(100), index=True)
    sku: Mapped[str] = mapped_column(String(100), index=True)
    order_id: Mapped[str | None] = mapped_column(String(36), unique=True)
    payload: Mapped[dict] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DealEventRow(Base):
    __tablename__ = "deal_events"
    __table_args__ = (
        UniqueConstraint("deal_id", "sequence_number", name="uq_deal_event_sequence"),
    )

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("deals.deal_id", ondelete="CASCADE"),
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    actor: Mapped[str] = mapped_column(String(200))
    details: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class OrganizationRow(Base):
    __tablename__ = "organizations"

    organization_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tax_id: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AgentRegistrationRow(Base):
    __tablename__ = "agent_registrations"

    registration_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("organizations.organization_id", ondelete="CASCADE"),
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    endpoint_url: Mapped[str] = mapped_column(String(500))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SQLAlchemyDealStore:
    """Persistent deal repository with an append-only event table."""

    def __init__(self, database_url: str) -> None:
        url = make_url(database_url)
        if url.drivername.startswith("sqlite") and url.database not in {
            None,
            ":memory:",
        }:
            Path(url.database).parent.mkdir(parents=True, exist_ok=True)
        engine_options: dict = {"pool_pre_ping": True}
        if database_url.endswith(":memory:"):
            from sqlalchemy.pool import StaticPool

            engine_options["poolclass"] = StaticPool
        self._engine: AsyncEngine = create_async_engine(
            database_url,
            **engine_options,
        )
        self._sessions = async_sessionmaker(self._engine, expire_on_commit=False)
        self._initialized = False
        self._initialize_lock = asyncio.Lock()

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._initialize_lock:
            if self._initialized:
                return
            async with self._engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            self._initialized = True

    async def close(self) -> None:
        await self._engine.dispose()

    async def put(self, deal: DealRecord) -> None:
        await self.initialize()
        deal_id = str(deal.deal_id)
        payload = deal.model_dump(mode="json", exclude={"events"})
        async with self._sessions.begin() as session:
            row = await session.get(DealRow, deal_id)
            if row is None:
                row = DealRow(
                    deal_id=deal_id,
                    status=deal.status.value,
                    customer_id=deal.intent.customer_id,
                    sku=deal.intent.product.sku,
                    order_id=str(deal.order_id) if deal.order_id else None,
                    payload=payload,
                    version=1,
                    created_at=deal.created_at,
                    updated_at=deal.updated_at,
                )
                session.add(row)
                await session.flush()
                existing_event_count = 0
            else:
                existing_event_count = (
                    await session.execute(
                        select(DealEventRow.sequence_number)
                        .where(DealEventRow.deal_id == deal_id)
                        .order_by(DealEventRow.sequence_number.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none() or 0
                row.status = deal.status.value
                row.customer_id = deal.intent.customer_id
                row.sku = deal.intent.product.sku
                row.order_id = str(deal.order_id) if deal.order_id else None
                row.payload = payload
                row.version += 1
                row.updated_at = deal.updated_at

            for sequence_number, event in enumerate(deal.events, start=1):
                if sequence_number <= existing_event_count:
                    continue
                session.add(
                    DealEventRow(
                        deal_id=deal_id,
                        sequence_number=sequence_number,
                        event_type=event.event_type,
                        actor=event.actor,
                        details=event.details,
                        created_at=event.created_at,
                    )
                )

    async def get(self, deal_id: UUID) -> DealRecord:
        await self.initialize()
        async with self._sessions() as session:
            row = await session.get(DealRow, str(deal_id))
            if row is None:
                raise DealNotFoundError(str(deal_id))
            return await self._to_record(session, row)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[DealRecord]:
        await self.initialize()
        statement = select(DealRow).order_by(DealRow.updated_at.desc())
        if status is not None:
            statement = statement.where(DealRow.status == status)
        statement = statement.offset(offset).limit(limit)
        async with self._sessions() as session:
            rows: Sequence[DealRow] = (
                await session.execute(statement)
            ).scalars().all()
            return [await self._to_record(session, row) for row in rows]

    async def _to_record(self, session, row: DealRow) -> DealRecord:
        event_rows = (
            await session.execute(
                select(DealEventRow)
                .where(DealEventRow.deal_id == row.deal_id)
                .order_by(DealEventRow.sequence_number)
            )
        ).scalars().all()
        payload = dict(row.payload)
        payload["events"] = [
            {
                "event_type": event.event_type,
                "actor": event.actor,
                "details": event.details,
                "created_at": event.created_at,
            }
            for event in event_rows
        ]
        return DealRecord.model_validate(payload)

    async def put_organization(self, organization: Organization) -> None:
        await self.initialize()
        async with self._sessions.begin() as session:
            existing = (
                await session.execute(
                    select(OrganizationRow).where(
                        OrganizationRow.tax_id == organization.tax_id
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise ValueError("Organization with this tax ID already exists")
            session.add(
                OrganizationRow(
                    organization_id=str(organization.organization_id),
                    tax_id=organization.tax_id,
                    payload=organization.model_dump(mode="json"),
                    created_at=organization.created_at,
                )
            )

    async def list_organizations(self) -> Sequence[Organization]:
        await self.initialize()
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(OrganizationRow).order_by(
                        OrganizationRow.created_at.desc()
                    )
                )
            ).scalars().all()
            return [Organization.model_validate(row.payload) for row in rows]

    async def get_organization(self, organization_id: UUID) -> Organization:
        await self.initialize()
        async with self._sessions() as session:
            row = await session.get(OrganizationRow, str(organization_id))
            if row is None:
                raise DealNotFoundError(str(organization_id))
            return Organization.model_validate(row.payload)

    async def put_agent_registration(
        self,
        registration: AgentRegistration,
    ) -> None:
        await self.initialize()
        async with self._sessions.begin() as session:
            existing = (
                await session.execute(
                    select(AgentRegistrationRow).where(
                        AgentRegistrationRow.agent_id == registration.agent_id
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                existing.status = registration.status.value
                existing.endpoint_url = registration.endpoint_url
                existing.payload = registration.model_dump(mode="json")
            else:
                session.add(
                    AgentRegistrationRow(
                        registration_id=str(registration.registration_id),
                        organization_id=str(registration.organization_id),
                        agent_id=registration.agent_id,
                        status=registration.status.value,
                        endpoint_url=registration.endpoint_url,
                        payload=registration.model_dump(mode="json"),
                        created_at=registration.created_at,
                    )
                )

    async def list_agent_registrations(self) -> Sequence[AgentRegistration]:
        await self.initialize()
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(AgentRegistrationRow).order_by(
                        AgentRegistrationRow.created_at.desc()
                    )
                )
            ).scalars().all()
            return [
                AgentRegistration.model_validate(row.payload)
                for row in rows
            ]
