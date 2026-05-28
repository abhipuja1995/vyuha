from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from vyuha.config import settings
from vyuha.db import TestCaseRepo, get_db

router = APIRouter()

DbDep = Annotated[AsyncSession, Depends(get_db)]

_ALLOWED = {".wav", ".mp3", ".ogg", ".flac", ".m4a"}
_MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
}


def _storage_path(key: str) -> Path:
    base = Path(settings.audio_storage_path)
    base.mkdir(parents=True, exist_ok=True)
    return base / key


def _node_key(test_id: str, node_id: str, ext: str) -> str:
    return f"{test_id}__{node_id}{ext}"


@router.post("/{test_id}/nodes/{node_id}/audio", summary="Upload audio for a conversation node")
async def upload_node_audio(
    test_id: str,
    node_id: str,
    db: DbDep,
    file: UploadFile = File(..., description="WAV, MP3, OGG, FLAC or M4A file"),
) -> dict:
    ext = Path(file.filename or "audio.wav").suffix.lower()
    if ext not in _ALLOWED:
        raise HTTPException(400, f"Unsupported format '{ext}'. Accepted: {sorted(_ALLOWED)}")

    tc = await TestCaseRepo(db).get(test_id)
    if not tc:
        raise HTTPException(404, f"Test case {test_id} not found")
    if not tc.conversation_graph.get_node(node_id):
        raise HTTPException(404, f"Node {node_id} not found in test case {test_id}")

    key = _node_key(test_id, node_id, ext)
    content = await file.read()
    _storage_path(key).write_bytes(content)

    ok = await TestCaseRepo(db).patch_node_audio(test_id, node_id, key)
    if not ok:
        raise HTTPException(500, "Failed to update test case")

    return {"test_id": test_id, "node_id": node_id, "audio_file": key, "size_bytes": len(content)}


@router.get("/{test_id}/nodes/{node_id}/audio", summary="Download audio for a conversation node")
async def get_node_audio(test_id: str, node_id: str, db: DbDep) -> FileResponse:
    tc = await TestCaseRepo(db).get(test_id)
    if not tc:
        raise HTTPException(404, f"Test case {test_id} not found")
    node = tc.conversation_graph.get_node(node_id)
    if not node:
        raise HTTPException(404, f"Node {node_id} not found")
    if not node.audio_file:
        raise HTTPException(404, "No audio uploaded for this node")

    path = _storage_path(node.audio_file)
    if not path.exists():
        raise HTTPException(404, "Audio file missing from storage")

    return FileResponse(path, media_type=_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"))


@router.delete("/{test_id}/nodes/{node_id}/audio", summary="Remove audio from a conversation node")
async def delete_node_audio(test_id: str, node_id: str, db: DbDep) -> dict:
    tc = await TestCaseRepo(db).get(test_id)
    if not tc:
        raise HTTPException(404, f"Test case {test_id} not found")
    node = tc.conversation_graph.get_node(node_id)
    if not node or not node.audio_file:
        raise HTTPException(404, "No audio for this node")

    path = _storage_path(node.audio_file)
    if path.exists():
        path.unlink()

    await TestCaseRepo(db).patch_node_audio(test_id, node_id, None)
    return {"deleted": True, "test_id": test_id, "node_id": node_id}
