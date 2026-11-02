import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models._base import IdMixin, pg_enum
from app.models.enums import StatusPeriodo


class Periodo(IdMixin, Base):
    __tablename__ = "periodo"

    empresa_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("empresa.id"), nullable=False
    )
    ano: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[StatusPeriodo] = mapped_column(
        pg_enum(StatusPeriodo, "status_periodo"), default=StatusPeriodo.ABERTO
    )
    fechado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fechado_por: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
