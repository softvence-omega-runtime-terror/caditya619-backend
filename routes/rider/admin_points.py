from fastapi import APIRouter, Depends, HTTPException, Form, Request
from applications.user.rider import RiderFeesAndBonuses, RiderProfile
from applications.user.models import User
from app.token import get_current_user
from tortoise.contrib.pydantic import pydantic_model_creator
from .notifications import send_notification
from app.utils.translator import translate





from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=['Admin Rider Points'])




RiderFeesAndBonuses_Pydantic = pydantic_model_creator(RiderFeesAndBonuses, name="RiderFeesAndBonuses")





@router.post("/rider-fees-and-bonus-rate", response_model=RiderFeesAndBonuses_Pydantic)
async def rider_fees_and_bonus_rate(
    request:Request,
    base_salary : float = Form(),
    delivery_fee: float = Form(),
    distance_bonus_per_km: float = Form(),
    weekly_bonus: float = Form(),
    referral_bonus: float = Form(),
    excellence_bonus: float = Form(),
    user: User = Depends(get_current_user),
    ):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
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

    result = await RiderFeesAndBonuses_Pydantic.from_tortoise_orm(fees_obj)

    return translate(result.dict(),lang)


@router.get("/rider-fees-and-bonus-rate", response_model=RiderFeesAndBonuses_Pydantic)
async def get_rider_fees_and_bonus_rate(request:Request, user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    if not user.is_superuser:
        raise HTTPException(403, "Not authorized")
    fees_obj = await RiderFeesAndBonuses.filter(id=1).first()
    if fees_obj is None:
        raise HTTPException(status_code=404, detail="No data found")
    result = await RiderFeesAndBonuses_Pydantic.from_tortoise_orm(fees_obj)
    return translate(result.dict(),lang)



@router.put("/rider-fees-and-bonus-rate/{id}", response_model=RiderFeesAndBonuses_Pydantic)
async def update_rider_fees_and_bonus_rate(request:Request,
                                            id:int,
                                            base_salary : float = Form(None),
                                            delivery_fee: float = Form(None),
                                            distance_bonus_per_km: float = Form(None),
                                            weekly_bonus: float = Form(None),
                                            referral_bonus: float = Form(None),
                                            excellence_bonus: float = Form(None),
                                            user: User = Depends(get_current_user)
                                        ):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
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


    result = await RiderFeesAndBonuses_Pydantic.from_tortoise_orm(fees_obj)
    return translate(result.dict(),lang)
    
    


@router.get("/rider-document-check/{rider_id}", response_model=dict)
async def check_rider_document(request:Request, rider_id:str, user:User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    if not user.is_superuser:
        raise HTTPException(403, "Not authorized")
    rider_profile = await RiderProfile.filter(user=rider_id).first()
    if not rider_profile:
        raise HTTPException(status_code=404, detail=f"No profile found for {rider_id}")
    
    return translate({
        "profile_image":rider_profile.profile_image,
        "driving_license":rider_profile.driving_license_document,
        "nid":rider_profile.national_id_document,
        "vehicle_registration":rider_profile.vehicle_registration_document,
        "vehicle_insurance":rider_profile.vehicle_insurance_document
    }, lang)



@router.put("/rider-document-approve/{rider_id}", response_model=dict)
async def approve_rider_document(request:Request, rider_id:str, is_verified:bool = Form(), user:User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "en").split(",")[0].strip().lower()
    if not user.is_superuser:
        raise HTTPException(403, "Not authorized")
    rider_profile = await RiderProfile.filter(user=rider_id).first()
    if not rider_profile:
        raise HTTPException(status_code=404, detail=f"No profile found for {rider_id}")
    if is_verified == True:
        rider_profile.is_verified = True
        await rider_profile.save()
        try:
            await send_notification(rider_id,"Your document has been verified","You are now eligible to earn points.")
        except Exception as e:
            print(e)
        return translate({"message":"Document approved successfully"}, lang)
    else:
        rider_profile.is_verified = False
        await rider_profile.save()
        try:
            await send_notification(rider_id,"Your document has been rejected","Please upload valid documents.")
        except Exception as e:
            print(e)
        return translate({"message":"Document rejected successfully"}, lang)

