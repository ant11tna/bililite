from pydantic import BaseModel
from typing import Optional, List, Literal

VideoState = Literal["NEW", "LATER", "STAR", "WATCHED", "HIDDEN"]


class VideoOut(BaseModel):
    bvid: str
    uid: int
    author_name: Optional[str] = None
    title: str
    pub_ts: int
    duration_sec: Optional[int] = None
    state: VideoState = "NEW"
    url: str
    cover_url: Optional[str] = None
    tname: Optional[str] = None
    view: Optional[int] = None
    tags: List[str] = []


class CreatorOut(BaseModel):
    uid: int
    name: Optional[str] = None
    group: Optional[str] = None
    priority: int = 0
    weight: int = 100
    last_fetch_at: Optional[str] = None


class VideoStateUpdateIn(BaseModel):
    bvid: str
    state: VideoState


class VideoStateOut(BaseModel):
    bvid: str
    state: VideoState
    updated_ts: int
