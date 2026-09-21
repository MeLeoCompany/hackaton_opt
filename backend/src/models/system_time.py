from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class SystemTime(Base):
    """Сдвиг системного времени в секундах: 0 — настоящее время (034)."""

    __tablename__ = "system_time"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    offset_seconds: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    # режим демонстрации: без него время не переводится и маршруты не синхронизируются (041)
    demo_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_mode_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    demo_mode_changed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
