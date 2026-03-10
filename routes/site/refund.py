from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from pydantic import BaseModel, Field

from app.auth import superuser_required
from applications.site.models import RefundPolicy

router = APIRouter(
    prefix="/refund",
    tags=["Refund Policy Info"],
)


def _serialize_refund_policy(refund_policy: RefundPolicy) -> dict:
    return {
        "id": refund_policy.id,
        "title": refund_policy.title,
        "details": refund_policy.details,
        "updated_at": refund_policy.updated_at,
    }


class RefundPolicyBulkItem(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    details: str = ""


@router.get("/", response_model=List[dict])
async def get_refund_policy():
    refund_policy_rows = await RefundPolicy.all().order_by("-updated_at")
    return [_serialize_refund_policy(item) for item in refund_policy_rows]


@router.post("/", response_model=dict, dependencies=[Depends(superuser_required)])
async def create_or_update_refund_policy(
    title: str = Form(...),
    details: str = Form(""),
):
    refund_policy = await RefundPolicy.get_or_none(title=title.strip())

    if refund_policy:
        refund_policy.details = details
    else:
        refund_policy = await RefundPolicy.create(title=title.strip(), details=details)
    await refund_policy.save()
    return _serialize_refund_policy(refund_policy)


@router.post("/bulk", response_model=dict, dependencies=[Depends(superuser_required)])
async def create_or_update_refund_policy_bulk(payload: List[RefundPolicyBulkItem]):
    if not payload:
        raise HTTPException(status_code=422, detail="Payload cannot be empty")

    created_count = 0
    updated_count = 0
    data: List[dict] = []

    for item in payload:
        title = item.title.strip()
        if not title:
            raise HTTPException(status_code=422, detail="Title cannot be empty")

        refund_policy = await RefundPolicy.get_or_none(title=title)
        if refund_policy:
            refund_policy.details = item.details
            await refund_policy.save()
            updated_count += 1
        else:
            refund_policy = await RefundPolicy.create(title=title, details=item.details)
            created_count += 1

        data.append(_serialize_refund_policy(refund_policy))

    return {
        "success": True,
        "message": "Refund policies processed successfully",
        "created_count": created_count,
        "updated_count": updated_count,
        "data": data,
    }


@router.patch("/{refund_policy_id}", response_model=dict, dependencies=[Depends(superuser_required)])
async def patch_refund_policy(
    refund_policy_id: int,
    title: Optional[str] = Form(None),
    details: Optional[str] = Form(None),
):
    refund_policy = await RefundPolicy.get_or_none(id=refund_policy_id)
    if not refund_policy:
        raise HTTPException(status_code=404, detail="Refund policy entry not found")

    if title is not None and title.strip():
        refund_policy.title = title.strip()
    if details is not None:
        refund_policy.details = details

    await refund_policy.save()
    return _serialize_refund_policy(refund_policy)


@router.delete("/{refund_policy_id}", response_model=dict, dependencies=[Depends(superuser_required)])
async def delete_refund_policy(refund_policy_id: int):
    refund_policy = await RefundPolicy.get_or_none(id=refund_policy_id)
    if not refund_policy:
        raise HTTPException(status_code=404, detail="Refund policy entry not found")
    await refund_policy.delete()
    return {"status": "success", "message": "Refund policy deleted"}
