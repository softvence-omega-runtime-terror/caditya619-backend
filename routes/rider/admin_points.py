from fastapi import APIRouter, Depends, HTTPException, Form
from applications.user.rider import RiderFeesAndBonuses
from applications.user.models import User
from app.token import get_current_user
from tortoise.contrib.pydantic import pydantic_model_creator





from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=['Admin Rider Points'])




RiderFeesAndBonuses_Pydantic = pydantic_model_creator(RiderFeesAndBonuses, name="RiderFeesAndBonuses")


@router.get("/test-admin-points/")
async def test_admin_points():
    return {"message": "Admin Rider Points route is working!"}



@router.post("/rider-fees-and-bonus-rate", response_model=RiderFeesAndBonuses_Pydantic)
async def rider_fees_and_bonus_rate(
    base_salary : float = Form(),
    delivery_fee: float = Form(),
    distance_bonus_per_km: float = Form(),
    weekly_bonus: float = Form(),
    referral_bonus: float = Form(),
    excellence_bonus: float = Form(),
    user: User = Depends(get_current_user)
    ):
    if not user.is_superuser:
        raise HTTPException(403, "Not authorized")
    fees_obj, created = await RiderFeesAndBonuses.get_or_create(id=1)
    if base_salary is not None:
        fees_obj.base_salary = base_salary
    if delivery_fee is not None:
        fees_obj.delivery_fee = delivery_fee
    if distance_bonus_per_km is not None:
        fees_obj.distance_bonus_per_km = distance_bonus_per_km
    if weekly_bonus is not None:
        fees_obj.weekly_bonus = weekly_bonus
    if referral_bonus is not None:
        fees_obj.referral_bonus = referral_bonus
    if excellence_bonus is not None:
        fees_obj.excellence_bonus = excellence_bonus
    await fees_obj.save()

    return await RiderFeesAndBonuses_Pydantic.from_tortoise_orm(fees_obj)


@router.get("/rider-fees-and-bonus-rate", response_model=RiderFeesAndBonuses_Pydantic)
async def get_rider_fees_and_bonus_rate(user: User = Depends(get_current_user)):
    if not user.is_superuser:
        raise HTTPException(403, "Not authorized")
    fees_obj = await RiderFeesAndBonuses.filter(id=1).first()
    if fees_obj is None:
        raise HTTPException(status_code=404, detail="No data found")
    return await RiderFeesAndBonuses_Pydantic.from_tortoise_orm(fees_obj)



@router.put("/rider-fees-and-bonus-rate/{id}", response_model=RiderFeesAndBonuses_Pydantic)
async def update_rider_fees_and_bonus_rate(id:int,
                                            base_salary : float = Form(None),
                                            delivery_fee: float = Form(None),
                                            distance_bonus_per_km: float = Form(None),
                                            weekly_bonus: float = Form(None),
                                            referral_bonus: float = Form(None),
                                            excellence_bonus: float = Form(None),
                                            user: User = Depends(get_current_user)
                                        ):
    if not user.is_superuser:
        raise HTTPException(403, "Not authorized")
    fees_obj = await RiderFeesAndBonuses.filter(id=id).first()
    if fees_obj is None:
        raise HTTPException(status_code=404, detail="No data found")
    if base_salary is not None:
        fees_obj.base_salary = base_salary
    if delivery_fee is not None:
        fees_obj.delivery_fee = delivery_fee
    if distance_bonus_per_km is not None:
        fees_obj.distance_bonus_per_km = distance_bonus_per_km
    if weekly_bonus is not None:
        fees_obj.weekly_bonus = weekly_bonus
    if referral_bonus is not None:
        fees_obj.referral_bonus = referral_bonus
    if excellence_bonus is not None:
        fees_obj.excellence_bonus = excellence_bonus

    await fees_obj.save()


    return await RiderFeesAndBonuses_Pydantic.from_tortoise_orm(fees_obj)
    
    


