# SPDX-License-Identifier: AGPL-3.0-or-later
"""Application database models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (UniqueConstraint("name", name="uq_vendors_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    contact = Column(String, nullable=True)
    role = Column(String, nullable=False, server_default="contact")  # compat: derived from is_vendor
    # Flags
    is_vendor = Column(Integer, nullable=False, server_default="0")  # 0/1 (SQLite boolean)
    is_org = Column(Integer, nullable=True, default=None)  # 0/1 (SQLite boolean); NULL allowed
    organization_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    meta = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    organization = relationship("Vendor", remote_side=[id], uselist=False)


class Item(Base):
    __tablename__ = "items"
    __table_args__ = (
        CheckConstraint(
            "dimension in ('length','area','volume','weight','count')",
            name="ck_items_dimension",
        ),
    )

    # TODO(next schema bump): consider AUTOINCREMENT here to avoid id reuse after deletes
    id = Column(Integer, primary_key=True, index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    sku = Column(String, nullable=True)
    name = Column(String, nullable=False)
    uom = Column(String, nullable=False, default="ea")          # display unit (legacy)
    dimension = Column(String, nullable=False, default="count")
    qty_stored = Column(Integer, nullable=False, default=0)      # canonical on-hand (base int)
    price = Column(Float, default=0)
    is_product = Column(Boolean, nullable=False, server_default="0")
    notes = Column(Text, nullable=True)
    item_type = Column(String, nullable=True)
    location = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ItemBatch(Base):
    __tablename__ = "item_batches"

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    qty_initial = Column(Integer, nullable=False)
    qty_remaining = Column(Integer, nullable=False)
    unit_cost_cents = Column(Integer, nullable=False)
    source_kind = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    is_oversold = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class ItemMovement(Base):
    __tablename__ = "item_movements"
    __table_args__ = (
        CheckConstraint(
            "NOT (source_kind='manufacturing' AND is_oversold=1)",
            name="ck_item_movements_no_mfg_oversell",
        ),
    )

    id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False, index=True)
    batch_id = Column(Integer, ForeignKey("item_batches.id"), nullable=True)
    qty_change = Column(Integer, nullable=False)
    unit_cost_cents = Column(Integer, nullable=True, default=0)
    source_kind = Column(String, nullable=False)
    source_id = Column(String, nullable=True)
    is_oversold = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class CashEvent(Base):
    __tablename__ = "cash_events"

    id = Column(Integer, primary_key=True)
    kind = Column(String, nullable=False, index=True)
    category = Column(String, nullable=True, index=True)
    amount_cents = Column(Integer, nullable=False)

    item_id = Column(Integer, ForeignKey("items.id"), nullable=True, index=True)
    qty_base = Column(Integer, nullable=True)
    unit_price_cents = Column(Integer, nullable=True)

    source_kind = Column(String, nullable=True, index=True)
    source_id = Column(String, nullable=True, index=True)
    related_source_id = Column(String, nullable=True, index=True)

    notes = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


__all__ = [
    "Base",
    "Item",
    "ItemBatch",
    "ItemMovement",
    "CashEvent",
    "Vendor",
]

# Import recipe/manufacturing models to attach to the shared Base
from core.appdb.models_recipes import ManufacturingRun, Recipe, RecipeItem  # noqa: E402  # isort:skip

__all__ += ["Recipe", "RecipeItem", "ManufacturingRun"]
