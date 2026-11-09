from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Date, DateTime, Index, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class KfcAppInstallsDaily(Base):
    __tablename__ = "kfc_app_installs_daily"
    __table_args__ = (
        UniqueConstraint(
            "date",
            "platform",
            "account_id",
            "campaign",
            name="uq_kfc_app_installs_daily_natural_key",
        ),
        Index("ix_kfc_app_installs_daily_date_platform", "date", "platform"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[Date] = mapped_column(Date, nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False)
    campaign: Mapped[str] = mapped_column(Text, nullable=False)
    spend: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    installs: Mapped[float] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    raw_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
    )


class KfcAppInstallsSnapshot(Base):
    __tablename__ = "kfc_app_installs_snapshots"
    __table_args__ = (
        Index("ix_kfc_app_installs_snapshots_range_created", "from_date", "to_date", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_date: Mapped[Date] = mapped_column(Date, nullable=False)
    to_date: Mapped[Date] = mapped_column(Date, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )


class KfcAppInstallsShare(Base):
    __tablename__ = "kfc_app_installs_share"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    share_token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    shared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_oid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_by_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)


class KfcMundialSnapshot(Base):
    __tablename__ = "kfc_mundial_snapshots"
    __table_args__ = (
        Index("ix_kfc_mundial_snapshots_range_created", "from_date", "to_date", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_date: Mapped[Date] = mapped_column(Date, nullable=False)
    to_date: Mapped[Date] = mapped_column(Date, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )


class KfcMundialShare(Base):
    __tablename__ = "kfc_mundial_share"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    share_token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    shared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_oid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_by_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)


class KfcMartesLocoSnapshot(Base):
    __tablename__ = "kfc_martes_loco_snapshots"
    __table_args__ = (
        Index(
            "ix_kfc_martes_loco_snapshots_range_created",
            "from_date",
            "to_date",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_date: Mapped[Date] = mapped_column(Date, nullable=False)
    to_date: Mapped[Date] = mapped_column(Date, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
    )


class KfcMartesLocoShare(Base):
    __tablename__ = "kfc_martes_loco_share"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    share_token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    shared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_oid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_by_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)

class KfcOnionMundialSnapshot(Base):
    __tablename__ = "kfc_onion_mundial_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    from_date: Mapped[Date] = mapped_column(Date, nullable=False)
    to_date: Mapped[Date] = mapped_column(Date, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)

class KfcOnionMundialShare(Base):
    __tablename__ = "kfc_onion_mundial_share"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    share_token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    shared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_oid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_by_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)


class KfcReporteShare(Base):
    __tablename__ = "kfc_reporte_share"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    share_token: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    shared_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_oid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_by_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
