import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Numeric, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models._base import IdMixin, TimestampMixin, pg_enum
from app.models.enums import OrigemLancamento, StatusLancamento


class Lancamento(IdMixin, TimestampMixin, Base):
    __tablename__ = "lancamento"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False
    )
    numero: Mapped[int | None] = mapped_column(BigInteger)
    data: Mapped[date] = mapped_column(Date, nullable=False)
    historico: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[StatusLancamento] = mapped_column(
        pg_enum(StatusLancamento, "status_lancamento"), default=StatusLancamento.RASCUNHO
    )
    origem: Mapped[OrigemLancamento] = mapped_column(
        pg_enum(OrigemLancamento, "origem_lancamento"), default=OrigemLancamento.MANUAL
    )
    chave_externa: Mapped[str | None] = mapped_column(String)
    estorno_de_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    estornado_por_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    criado_por: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id"), nullable=False
    )
    efetivado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    efetivado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id"))

    partidas: Mapped[list["Partida"]] = relationship(
        back_populates="lancamento",
        cascade="all, delete-orphan",
        order_by="Partida.ordem",
        lazy="selectin",
    )


class Partida(IdMixin, Base):
    __tablename__ = "partida"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False
    )
    lancamento_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lancamento.id", ondelete="CASCADE"), nullable=False
    )
    conta_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conta.id"), nullable=False
    )
    centro_custo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("centro_custo.id")
    )
    ordem: Mapped[int] = mapped_column(SmallInteger, default=0)
    debito: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal(0))
    credito: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal(0))
    historico_complementar: Mapped[str | None] = mapped_column(String)

    lancamento: Mapped[Lancamento] = relationship(back_populates="partidas")
