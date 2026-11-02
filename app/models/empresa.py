import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models._base import IdMixin, TimestampMixin, pg_enum
from app.models.enums import PapelEmpresa, RegimeTributario


class Empresa(IdMixin, TimestampMixin, Base):
    __tablename__ = "empresa"

    razao_social: Mapped[str] = mapped_column(String, nullable=False)
    nome_fantasia: Mapped[str | None] = mapped_column(String)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, nullable=False)
    regime_tributario: Mapped[RegimeTributario] = mapped_column(
        pg_enum(RegimeTributario, "regime_tributario"), nullable=False
    )
    inicio_exercicio_mes: Mapped[int] = mapped_column(SmallInteger, default=1)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    proximo_numero_lancamento: Mapped[int] = mapped_column(BigInteger, default=1)

    usuarios: Mapped[list["UsuarioEmpresa"]] = relationship(back_populates="empresa")


class UsuarioEmpresa(Base):
    __tablename__ = "usuario_empresa"

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    empresa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("empresa.id", ondelete="CASCADE"), primary_key=True
    )
    papel: Mapped[PapelEmpresa] = mapped_column(pg_enum(PapelEmpresa, "papel_empresa"), nullable=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    usuario: Mapped["Usuario"] = relationship(back_populates="empresas")
    empresa: Mapped[Empresa] = relationship(back_populates="usuarios")


from app.models.usuario import Usuario
