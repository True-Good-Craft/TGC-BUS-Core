# SPDX-License-Identifier: AGPL-3.0-or-later
from __future__ import annotations

import json
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.appdb.models import Vendor as VendorModel
from core.appdb.session import get_db
from core.api.schemas.vendors import VendorCreate, VendorOut, VendorUpdate
from core.api.security import require_write_access
from core.auth.dependencies import require_permission
from core.auth.permissions import PERMISSION_CONTACTS_READ, PERMISSION_CONTACTS_WRITE
from core.policy.guard import require_owner_commit
from tgc.security import require_token_ctx

router = APIRouter(tags=["vendors"])


def _parse_bool(value: Any) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int,)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return None


def _apply_defaults(payload: dict, facade: str, existing: Optional[VendorModel] = None) -> dict:
    data = payload.copy()
    data.pop("kind", None)
    is_vendor_flag = _parse_bool(data.get("is_vendor"))
    role_val = data.get("role")
    if is_vendor_flag is None and role_val is not None:
        role_normalized = str(role_val).strip().lower()
        is_vendor_flag = role_normalized in {"vendor", "both"}
    if is_vendor_flag is None:
        is_vendor_flag = bool(existing.is_vendor) if existing is not None else facade == "vendors"
    data["is_vendor"] = 1 if is_vendor_flag else 0
    data["role"] = "vendor" if is_vendor_flag else "contact"

    if "is_org" in data:
        is_org_flag = _parse_bool(data.get("is_org"))
        if is_org_flag is None:
            data["is_org"] = None
        else:
            data["is_org"] = 1 if is_org_flag else 0
    elif existing is None:
        data["is_org"] = 0

    if "meta" in data and data.get("meta") is not None and not isinstance(
        data.get("meta"), str
    ):
        try:
            data["meta"] = json.dumps(data.get("meta"))
        except Exception:
            data["meta"] = None
    return data


def _query_filters(q: Optional[str], role: Optional[str], organization_id: Optional[int], role_in: Optional[str], is_vendor: Optional[Any], is_org: Optional[Any]):
    filters = []
    if q:
        like = f"%{q}%"
        filters.append(or_(VendorModel.name.ilike(like), VendorModel.contact.ilike(like)))
    if role and role.lower() != "any":
        filters.append(VendorModel.role == role.lower())
    if organization_id is not None:
        filters.append(VendorModel.organization_id == organization_id)
    vendor_flag = _parse_bool(is_vendor)
    if vendor_flag is not None:
        filters.append(VendorModel.is_vendor == (1 if vendor_flag else 0))
    org_flag = _parse_bool(is_org)
    if org_flag is True:
        filters.append(VendorModel.is_org == 1)
    elif org_flag is False:
        filters.append(or_(VendorModel.is_org == 0, VendorModel.is_org.is_(None)))
    if role_in:
        roles = [r.strip().lower() for r in role_in.split(",") if r.strip()]
        if roles:
            filters.append(VendorModel.role.in_(roles))
    return filters


def _crud_routes(prefix: str, facade: str):
    @router.get(prefix, response_model=List[VendorOut])
    def list_vendors(
        q: Optional[str] = None,
        role: Optional[str] = Query(None, description="vendor|contact|both|any"),
        role_in: Optional[str] = Query(None, description="CSV of roles (compat)"),
        is_vendor: Optional[str] = Query(None, description="Filter by vendor flag"),
        is_org: Optional[str] = Query(None, description="Filter by organization flag"),
        organization_id: Optional[int] = Query(None, description="Filter by parent org ID"),
        db: Session = Depends(get_db),
        _permission=Depends(require_permission(PERMISSION_CONTACTS_READ)),
        _token: str = Depends(require_token_ctx),
    ):
        query = db.query(VendorModel)
        for f in _query_filters(q, role, organization_id, role_in, is_vendor, is_org):
            query = query.filter(f)
        return query.order_by(VendorModel.name.asc()).all()

    @router.get(f"{prefix}" + "/{id}", response_model=VendorOut)
    def get_vendor(
        id: int,
        db: Session = Depends(get_db),
        _permission=Depends(require_permission(PERMISSION_CONTACTS_READ)),
        _token: str = Depends(require_token_ctx),
    ):
        v = db.query(VendorModel).get(id)
        if not v:
            raise HTTPException(status_code=404, detail="Not found")
        return v

    @router.post(prefix, response_model=VendorOut, status_code=201)
    def create_vendor(
        payload: VendorCreate,
        request: Request,
        db: Session = Depends(get_db),
        _writes: None = Depends(require_write_access),
        _permission=Depends(require_permission(PERMISSION_CONTACTS_WRITE)),
        _token: str = Depends(require_token_ctx),
    ):
        require_owner_commit(request)
        data = _apply_defaults(payload.model_dump(exclude_unset=True), facade)
        v = VendorModel(**data)
        db.add(v)
        db.commit()
        db.refresh(v)
        return v

    @router.put(f"{prefix}" + "/{id}", response_model=VendorOut)
    def update_vendor(
        id: int,
        payload: VendorUpdate,
        request: Request,
        db: Session = Depends(get_db),
        _writes: None = Depends(require_write_access),
        _permission=Depends(require_permission(PERMISSION_CONTACTS_WRITE)),
        _token: str = Depends(require_token_ctx),
    ):
        require_owner_commit(request)
        v = db.query(VendorModel).get(id)
        if not v:
            raise HTTPException(status_code=404, detail="Not found")
        updates = _apply_defaults(
            payload.model_dump(exclude_unset=True, exclude_none=True), facade, existing=v
        )
        for k, val in updates.items():
            setattr(v, k, val)
        db.add(v)
        db.commit()
        db.refresh(v)
        return v

    @router.delete(f"{prefix}" + "/{id}", status_code=204)
    def delete_vendor(
        id: int,
        request: Request,
        cascade_children: bool = Query(False),
        db: Session = Depends(get_db),
        _writes: None = Depends(require_write_access),
        _permission=Depends(require_permission(PERMISSION_CONTACTS_WRITE)),
        _token: str = Depends(require_token_ctx),
    ):
        require_owner_commit(request)
        v = db.query(VendorModel).get(id)
        if not v:
            raise HTTPException(status_code=404, detail="Not found")

        # If org with dependents: either cascade delete or auto-null children
        if bool(v.is_org):
            children = db.query(VendorModel).filter(VendorModel.organization_id == id)
            if cascade_children:
                children.delete(synchronize_session=False)
            else:
                children.update({"organization_id": None}, synchronize_session=False)

        db.delete(v)
        db.commit()
        return


# Mount façade routes
_crud_routes("/vendors", "vendors")
_crud_routes("/contacts", "contacts")
