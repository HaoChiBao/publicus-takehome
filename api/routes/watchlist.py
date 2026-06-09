"""Saved watchlists — programs and competitors per session."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_repo

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistItemIn(BaseModel):
    entity_type: str  # 'program' | 'recipient'
    entity_id: str


@router.get("/{session_id}")
async def get_watchlist(session_id: str):
    repo = await get_repo()
    return await repo.get_watchlist(session_id)


@router.post("/{session_id}")
async def add_watchlist_item(session_id: str, item: WatchlistItemIn):
    if item.entity_type not in ("program", "recipient"):
        raise HTTPException(status_code=400, detail="entity_type must be program or recipient")
    repo = await get_repo()
    return await repo.add_watchlist_item(session_id, item.entity_type, item.entity_id)


@router.delete("/{session_id}/{entity_type}/{entity_id}")
async def remove_watchlist_item(session_id: str, entity_type: str, entity_id: str):
    repo = await get_repo()
    return await repo.remove_watchlist_item(session_id, entity_type, entity_id)
