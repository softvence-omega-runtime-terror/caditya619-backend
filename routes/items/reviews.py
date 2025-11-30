from fastapi import APIRouter, HTTPException, Depends, Form
from typing import Optional, List
from applications.items.review import ItemReview
from applications.user.models import User
from app.auth import get_current_user

router = APIRouter(prefix="/reviews", tags=["Review"])

# -----------------------------
# Helper to serialize review + nested replies
# -----------------------------
async def serialize_review(review: ItemReview) -> dict:
    replies = []
    async for r in review.replies:
        replies.append(await serialize_review(r))

    return {
        "id": review.id,
        "item_id": review.item_id,
        "user_id": review.user_id,
        "rating": review.rating,
        "comment": review.comment,
        "parent_id": review.parent_id,
        "created_at": review.created_at,
        "updated_at": review.updated_at,
        "is_reply": review.is_reply,
        "replies": replies
    }

# -----------------------------
# CRUD Endpoints
# -----------------------------
@router.post("/", response_model=dict)
async def create_review(
    item: int = Form(...),
    rating: Optional[int] = Form(None),
    comment: Optional[str] = Form(None),
    parent: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user)
):
    parent_review = None
    if parent and parent.isdigit():
        parent_review = await ItemReview.get_or_none(id=int(parent))
        if not parent_review:
            raise HTTPException(status_code=404, detail="Parent review not found")
        rating = None  # Replies cannot have rating

    review = await ItemReview.create(
        item_id=item,
        user_id=current_user.id,
        rating=rating,
        comment=comment,
        parent=parent_review
    )

    return await serialize_review(review)


@router.get("/{review_id}", response_model=dict)
async def get_review(review_id: int):
    review = await ItemReview.get_or_none(id=review_id).prefetch_related("replies")
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return await serialize_review(review)


@router.get("/", response_model=List[dict])
async def list_reviews():
    reviews = await ItemReview.all().prefetch_related("replies")
    result = []
    for r in reviews:
        if not r.is_reply:  # only top-level reviews
            result.append(await serialize_review(r))
    return result


@router.put("/{review_id}", response_model=dict)
async def update_review(
    review_id: int,
    rating: Optional[int] = Form(None),
    comment: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user)
):
    review = await ItemReview.get_or_none(id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to update")

    if review.is_reply and rating is not None:
        raise HTTPException(status_code=400, detail="Replies cannot have ratings")

    if rating is not None:
        review.rating = rating
    if comment is not None:
        review.comment = comment

    await review.save()
    return await serialize_review(review)


@router.delete("/{review_id}", response_model=dict)
async def delete_review(review_id: int, current_user: User = Depends(get_current_user)):
    review = await ItemReview.get_or_none(id=review_id)
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not allowed to delete")
    await review.delete()
    return {"detail": "Review deleted"}
