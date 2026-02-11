from pydantic import BaseModel
from typing import Optional, List, Literal

VideoState = Literal["NEW", "READ", "LATER", "STAR", "WATCHED", "HIDDEN"]


class VideoOut(BaseModel):
    bvid: str
    uid: int
    author_name: Optional[str] = None  # ✅ 新增
    title: str
    pub_ts: int
    duration_sec: Optional[int] = None
    state: VideoState = "NEW"
    url: str
    cover_url: Optional[str] = None
    tname: Optional[str] = None
    view: Optional[int] = None
    tags: List[str] = []  # 若你愿意更规范：= Field(default_factory=list)


class VideoStateUpdateIn(BaseModel):
    bvid: str
    state: VideoState


class VideoStateOut(BaseModel):
    bvid: str
    state: VideoState
    updated_ts: int


class CreatorOut(BaseModel):
    uid: int
    author_name: Optional[str] = None
    enabled: bool
    priority: int = 0
    weight: int = 1


class CreatorUpdateIn(BaseModel):
    uid: int
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    weight: Optional[int] = None
