"""Simple user note endpoints backed by user preferences JSON."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import TokenPayload, get_current_user
from app.db.config import get_db
from app.db.models import User

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteCreateRequest(BaseModel):
    title: Optional[str] = Field(default="Quick Note")
    content: str = Field(..., min_length=1, max_length=5000)
    created_at: Optional[str] = None


async def get_current_user_from_db(
    current_token: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    user = db.query(User).filter(User.id == current_token.sub).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def _read_notes_from_preferences(user: User) -> list[dict]:
    preferences = dict(user.preferences or {})
    notes = preferences.get("notes") or []
    return notes if isinstance(notes, list) else []


@router.get("")
async def list_notes(current_user: User = Depends(get_current_user_from_db)) -> list[dict]:
    notes = _read_notes_from_preferences(current_user)
    return sorted(notes, key=lambda n: n.get("created_at") or "", reverse=True)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_note(
    request: NoteCreateRequest,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    note = {
        "id": str(uuid4()),
        "title": (request.title or "Quick Note").strip() or "Quick Note",
        "content": request.content.strip(),
        "created_at": request.created_at or datetime.utcnow().isoformat(),
    }

    preferences = dict(current_user.preferences or {})
    notes = _read_notes_from_preferences(current_user)
    notes.insert(0, note)
    preferences["notes"] = notes[:200]
    current_user.preferences = preferences

    db.add(current_user)
    db.commit()

    return note


@router.delete("/{note_id}", status_code=status.HTTP_200_OK)
async def delete_note(
    note_id: str,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> None:
    preferences = dict(current_user.preferences or {})
    notes = _read_notes_from_preferences(current_user)
    filtered = [note for note in notes if note.get("id") != note_id]

    if len(filtered) == len(notes):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    preferences["notes"] = filtered
    current_user.preferences = preferences

    db.add(current_user)
    db.commit()
