from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
from typing import Optional


class User(BaseModel):
    id: Optional[int] = None
    tg_id: int
    trial: bool = False
    vless_key: Optional[str] = None
    slot_id: Optional[int] = None
    subscription_end: Optional[datetime] = None

class Slot(BaseModel):
    slot_id: Optional[int] = None
    server_name: str
    ip: Optional[str] = None
    slot_number: int
    tg_id: Optional[int] = None
    assigned_at: Optional[datetime] = None

class Server(BaseModel):
    id: Optional[int] = None
    name: str
    ip: Optional[str] = None
    region: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    free_slots: int = Field(default=40, ge=0, le=40)
