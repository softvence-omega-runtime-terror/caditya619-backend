from fastapi import APIRouter, Depends, HTTPException, Form, UploadFile, File
from applications.user.models import User
from applications.user.rider import RiderProfile, RiderQuizAttempt, QuizQuestion, TrainingPDF, TrainingVideo
from app.token import get_current_user
import json
from datetime import datetime
from tortoise.contrib.pydantic import pydantic_model_creator
from typing import List, Dict
from typing import Optional
from app.utils.file_manager import save_file
from random import shuffle
from fastapi.responses import HTMLResponse
from fastapi.requests import Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.utils.translator import translate






from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

router = APIRouter(tags=['Rider Training'])


QuizeQusetionsPydantic = pydantic_model_creator(QuizQuestion, name="QuizQuestion")
QuizeQusetionsPydanticOut = pydantic_model_creator(QuizQuestion, name="QuizQuestionOut", exclude_readonly=True)






@router.post("/quiz/questions", response_model=QuizeQusetionsPydanticOut)
async def create_quiz_questions(request:Request,
                                    question : str = Form(...), 
                                    option_a : str = Form(...), 
                                    option_b : str = Form(...), 
                                    option_c : str = Form(...), 
                                    option_d : str = Form(...), 
                                    correct_answer : str = Form(...),
                                    explanation : Optional[str] = Form(""),
                                 current_user: User = Depends(get_current_user)
                                ):
    lang = request.headers.get("Accept-Language", "bn").split(",")[0].strip().lower()
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail=translate("Not authorized", lang))
    

    quiz_question = await QuizQuestion.create(
        question=question,
        option_a=option_a,
        option_b=option_b,
        option_c=option_c,
        option_d=option_d,
        correct_answer=correct_answer,
        explanation=explanation
    )

    await quiz_question.save()

    return await QuizeQusetionsPydanticOut.from_tortoise_orm(translate(quiz_question, lang))
    




# ------------------- 1. Start Quiz – Get Questions -------------------
@router.get("/start")
async def start_quiz(request:Request, current_user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "bn").split(",")[0].strip().lower()
    if not current_user.is_rider:
        raise HTTPException(status_code=403, detail=translate("Not authorized", lang))
    questions = await QuizQuestion.all()
    if not questions:
        raise HTTPException(404, translate("No quiz questions found", lang))

    # Shuffle options for each question (real exam feel)
    serialized = []
    for q in questions:
        options = [
            {"key": "A", "text": q.option_a},
            {"key": "B", "text": q.option_b},
            {"key": "C", "text": q.option_c},
            {"key": "D", "text": q.option_d},
        ]
        #shuffle(options)  # Randomize option order

        serialized.append({
            "id": q.id,
            "question": q.question,
            "options": options,
            "explanation": q.explanation  # Show after submit
        })

    return translate(obj={
        "total_questions": len(questions),
        "instructions": "Select one answer per question. Minimum 80% to pass.",
        "questions": serialized
    }, target_lang=lang)

# ------------------- 2. Submit Quiz – With Full Results -------------------
@router.post("/submit")
async def submit_quiz(
    request:Request,
    answers: Dict[str, str],  # {"1": "A", "3": "C", ...}
    current_user: User = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "bn").split(",")[0].strip().lower()
    if not current_user.is_rider:
        raise HTTPException(status_code=403, detail=translate("Not authorized", lang))
    rider = await RiderProfile.get(user=current_user)
    questions = await QuizQuestion.all()
    if not questions:
        raise HTTPException(404, translate("No questions available", lang))

    correct = 0
    results = []
    detailed_results = []

    for q in questions:
        user_answer = answers.get(str(q.id))
        is_correct = user_answer == q.correct_answer

        if is_correct:
            correct += 1

        results.append({
            "question_id": q.id,
            "your_answer": user_answer,
            "correct_answer": q.correct_answer,
            "is_correct": is_correct
        })

        # Full question with explanation
        detailed_results.append({
            "question": q.question,
            "your_answer": user_answer,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
            "is_correct": is_correct
        })

    score = int((correct / len(questions)) * 100)
    passed = score >= 80

    # Mark old attempts as not latest
    await RiderQuizAttempt.filter(rider=rider, is_latest=True).update(is_latest=False)

    # Save new attempt
    attempt = await RiderQuizAttempt.create(
        rider=rider,
        score=score,
        correct_answers=correct,
        total_questions=len(questions),
        passed=passed,
        is_latest=True
    )

    # Certify rider
    # if passed and not rider.is_certified:
    #     rider.is_certified = True
    #     rider.certified_at = datetime.utcnow()
    #     await rider.save()

        # Optional: Send FCM Push
        # await send_push(rider.id, "Certified!", "You passed the training quiz!")

    return translate({
        "attempt_id": attempt.id,
        "score": score,
        "correct": correct,
        "total": len(questions),
        "passed": passed,
        #"is_certified": rider.is_certified,
        "results": detailed_results
    }, lang)

# ------------------- 3. Get Past Attempts -------------------
@router.get("/attempts")
async def get_attempts(request:Request, current_user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "bn").split(",")[0].strip().lower()
    if not current_user.is_rider:
        raise HTTPException(status_code=403, detail=translate("Not authorized", lang))
    rider = await RiderProfile.get(user=current_user)
    attempts = await RiderQuizAttempt.filter(rider=rider).order_by("-attempted_at")
    
    return [
        translate({
            "id": a.id,
            "score": a.score,
            "passed": a.passed,
            "date": a.attempted_at.strftime("%Y-%m-%d %H:%M")
        }, lang)
        for a in attempts
    ]

templates = Jinja2Templates(directory="templates")

@router.get("/quiz-test", response_class=HTMLResponse)
async def quiz_test_page(request: Request):
    return templates.TemplateResponse("quiz_test_client.html", {"request": request})



@router.post("/upload/video")
async def upload_video(
    request: Request,
    title: str = Form(...),
    file: UploadFile = File(...),
    thumbnail: UploadFile = File(None),
    user = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "bn").split(",")[0].strip().lower()
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if file and file.filename:
         file_path = await save_file(
            file, upload_to="videos"
        )
         
    if thumbnail and thumbnail.filename:
         thumblin_path = await save_file(
            thumbnail, upload_to="thumbnails"
        )

    video = await TrainingVideo.create(
        title=title,
        video_file=file_path,
        thumbnail= thumblin_path,
        order=(await TrainingVideo.all().count()) + 1
    )
    return translate({"message": "Video uploaded", "id": video.id}, lang)

@router.post("/upload/pdf")
async def upload_pdf(
    request: Request,
    title: str = Form(...),
    file: UploadFile = File(...),
    user = Depends(get_current_user)
):
    lang = request.headers.get("Accept-Language", "bn").split(",")[0].strip().lower()
    if not user.is_superuser:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    if file and file.filename:
         file_path = await save_file(
            file, upload_to="training_pdfs"
        )

    pdf = await TrainingPDF.create(
        title=title,
        file=file_path,
        order=(await TrainingPDF.all().count()) + 1
    )
    return translate({"message": "PDF uploaded", "id": pdf.id}, lang)



@router.get("/videos")
async def get_videos(request:Request, current_user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "bn").split(",")[0].strip().lower()
    if not current_user.is_rider:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    videos = await TrainingVideo.filter(is_active=True).order_by("order")
    return [
        translate({
            "id": v.id,
            "title": v.title,
            "duration": v.duration,
            "video_url": v.video_file,
            "thumbnail": v.thumbnail,
        }, lang)
        for v in videos
    ]

@router.get("/pdfs")
async def get_pdfs(request:Request, current_user: User = Depends(get_current_user)):
    lang = request.headers.get("Accept-Language", "bn").split(",")[0].strip().lower()
    if not current_user.is_rider:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    pdfs = await TrainingPDF.filter(is_active=True).order_by("order")
    
    return [
        translate({
            "id": p.id,
            "title": p.title,
            "file_url": p.file
        }, lang)
        for p in pdfs
    ]

