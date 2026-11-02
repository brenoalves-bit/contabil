import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    empresa_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    acao: Mapped[str] = mapped_column(String, nullable=False)
    entidade: Mapped[str] = mapped_column(String, nullable=False)
    entidade_id: Mapped[str | None] = mapped_column(String)
    dados: Mapped[dict | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
