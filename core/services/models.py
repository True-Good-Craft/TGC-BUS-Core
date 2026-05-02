# Copyright (C) 2025 BUS Core Authors
# SPDX-License-Identifier: AGPL-3.0-or-later

# Copyright (C) 2025 True Good Craft
#
# This file is part of TGC BUS Core.
#
# TGC BUS Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# TGC BUS Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with TGC BUS Core.  If not, see <https://www.gnu.org/licenses/>.

"""SQLAlchemy models for BUS Core domain data."""

from __future__ import annotations

from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, String, Text, func

from core.appdb.engine import SessionLocal, get_engine, get_session
from core.appdb.models import Base, Item, Recipe, RecipeItem, Vendor


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=True)
    title = Column(String, nullable=False)
    status = Column(String, nullable=False, server_default="pending")
    due = Column(Date, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(String, nullable=False)
    entity_id = Column(Integer, nullable=False)
    reader_id = Column(String, nullable=False)
    label = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


# Ensure tables exist AFTER all models are defined
ENGINE = get_engine()
Base.metadata.create_all(bind=ENGINE)


__all__ = [
    "Attachment",
    "Base",
    "ENGINE",
    "Item",
    "Recipe",
    "RecipeItem",
    "SessionLocal",
    "Task",
    "Vendor",
    "get_session",
]
