from __future__ import annotations

import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .reality import Campaign, Lawyer, RealityError
from .telemetry import TelemetryStore

router = APIRouter(prefix="/bureau", tags=["Bureaucracy of Reality"])
campaign = Campaign(telemetry=TelemetryStore())


def prepare_lawyer():
    if isinstance(campaign.planner, Lawyer):
        campaign.planner.prepare()


class Command(BaseModel):
    action: str = Field(min_length=1, max_length=30)


class Tick(BaseModel):
    dx: float = Field(default=0, ge=-1, le=1, allow_inf_nan=False)
    dy: float = Field(default=0, ge=-1, le=1, allow_inf_nan=False)
    dt: float = Field(default=.1, ge=0, le=.2, allow_inf_nan=False)
    crouch: bool = False


class Wish(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex, pattern=r"^[A-Za-z0-9_-]{1,80}$")


def checked(fn, *args):
    try:
        return fn(*args)
    except RealityError as error:
        raise HTTPException(409, str(error)) from error


@router.post("/sessions", status_code=201)
def create_session():
    return campaign.create()


@router.get("/sessions/{sid}")
def get_session(sid: str):
    return checked(campaign.get, sid)


@router.post("/sessions/{sid}/command")
def command(sid: str, request: Command):
    return checked(campaign.command, sid, request.action)


@router.post("/sessions/{sid}/tick")
def tick(sid: str, request: Tick):
    return checked(campaign.tick, sid, request.dx, request.dy, request.dt, request.crouch)


@router.post("/sessions/{sid}/wish")
async def wish(sid: str, request: Wish):
    try:
        return await campaign.wish(sid, request.text, request.request_id)
    except RealityError as error:
        raise HTTPException(409, str(error)) from error
