"""V3 语音接口：录音转写、确认、语音播报与文件下载。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_principal
from app.api.responses import ok
from app.core.db import get_db
from app.core.storage import get_storage
from app.services import voice_service, voiceprint_service
from app.services.permission_service import Principal

router = APIRouter(prefix="/voice", tags=["voice"])

_MEDIA_TYPES = {"wav": "audio/wav", "mp3": "audio/mpeg"}


class ConfirmIn(BaseModel):
    transcript_id: int = Field(gt=0)
    final_text: str | None = Field(default=None, max_length=2000)


class TtsIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


@router.post("/asr")
def transcribe(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = voice_service.create_transcript(
        db,
        principal,
        file_name=file.filename or "voice.wav",
        data=file.file.read(),
    )
    return ok(request, data, status_code=201)


@router.post("/confirm")
def confirm(
    request: Request,
    payload: ConfirmIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = voice_service.confirm_transcript(
        db,
        principal,
        transcript_id=payload.transcript_id,
        final_text=payload.final_text,
    )
    return ok(request, data)


@router.post("/tts")
def synthesize(
    request: Request,
    payload: TtsIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    data = voice_service.synthesize_reply(db, principal, text=payload.text)
    return ok(request, data, status_code=201)


@router.get("/voiceprint")
def voiceprint_status(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, voiceprint_service.status(db, principal))


@router.post("/voiceprint")
def voiceprint_enroll(
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    samples = [file.file.read() for file in files]
    return ok(request, voiceprint_service.enroll(db, principal, samples=samples), status_code=201)


@router.delete("/voiceprint")
def voiceprint_remove(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    return ok(request, voiceprint_service.remove(db, principal))


@router.get("/files/{file_id}/download")
def download(
    file_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    voice_file = voice_service.get_voice_file(db, principal, file_id)
    data = get_storage().read(voice_file.file_path)
    return Response(
        content=data,
        media_type=_MEDIA_TYPES.get(voice_file.file_ext, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{voice_file.file_name}"'},
    )
