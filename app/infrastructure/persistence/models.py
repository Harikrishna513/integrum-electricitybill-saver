"""
SQLAlchemy ORM models — Milestone 7.

IMPORTANT
  These are persistence models (infrastructure), NOT domain models.
  Domain stays in app/domain/models as Pydantic objects.

SPRING ANALOGY
  @Entity classes in a persistence package, mapped from domain aggregates.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.infrastructure.persistence.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ConsumerORM(Base):
    __tablename__ = "consumers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    discom: Mapped[str] = mapped_column(String(64), default="BESCOM", index=True)
    rr_number: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    account_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # PII — local learning only; avoid logging this field
    consumer_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    bills: Mapped[list[BillAnalysisORM]] = relationship(back_populates="consumer")


class DocumentORM(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    original_filename: Mapped[str] = mapped_column(String(512))
    stored_filename: Mapped[str] = mapped_column(String(256), unique=True)
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    storage_path: Mapped[str] = mapped_column(String(1024))
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    bill_analysis: Mapped[BillAnalysisORM | None] = relationship(
        back_populates="document",
        uselist=False,
    )


class BillAnalysisORM(Base):
    """
    One analysis run for one uploaded bill document.

    Queryable scalar fields + JSON snapshots of full pipeline outputs.
    """

    __tablename__ = "bill_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("documents.id"), unique=True, index=True
    )
    consumer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("consumers.id"), nullable=True, index=True
    )

    model_name: Mapped[str] = mapped_column(String(128))
    discom: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    rr_number: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    account_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    tariff_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    classification_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    consistency_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    supported_by_app_v1: Mapped[bool | None] = mapped_column(nullable=True)

    billing_period: Mapped[str | None] = mapped_column(String(128), nullable=True)
    bill_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    units_consumed: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    sanctioned_load: Mapped[float | None] = mapped_column(Float, nullable=True)

    extraction_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    validation_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    classification_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    consistency_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    canonical_bill_json: Mapped[dict[str, Any]] = mapped_column(JSON)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    document: Mapped[DocumentORM] = relationship(back_populates="bill_analysis")
    consumer: Mapped[ConsumerORM | None] = relationship(back_populates="bills")
