import uuid

from sqlalchemy import Boolean, ForeignKey, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models._base import IdMixin, TimestampMixin, pg_enum
from app.models.enums import GrupoConta, NaturezaConta, TipoConta


class Conta(IdMixin, TimestampMixin, Base):
    __tablename__ = "conta"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(String, nullable=False)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    grupo: Mapped[GrupoConta] = mapped_column(pg_enum(GrupoConta, "grupo_conta"), nullable=False)
    natureza: Mapped[NaturezaConta] = mapped_column(
        pg_enum(NaturezaConta, "natureza_conta"), nullable=False
    )
    tipo: Mapped[TipoConta] = mapped_column(pg_enum(TipoConta, "tipo_conta"), nullable=False)
    conta_pai_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("conta.id"))
    nivel: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    codigo_referencial: Mapped[str | None] = mapped_column(String)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)

    pai: Mapped["Conta | None"] = relationship(remote_side="Conta.id", foreign_keys=[conta_pai_id])


class CentroCusto(IdMixin, TimestampMixin, Base):
    __tablename__ = "centro_custo"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False
    )
    codigo: Mapped[str] = mapped_column(String, nullable=False)
    nome: Mapped[str] = mapped_column(String, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
