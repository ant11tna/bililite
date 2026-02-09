from pydantic import BaseModel
from typing import Optional, List

class VideoOut(BaseModel):
    bvid: str
    uid: int
    author_name: Optional[str] = None  # ✅ 新增
    title: str
    pub_ts: int
    url: str
    cover_url: Optional[str] = None
    tname: Optional[str] = None
    view: Optional[int] = None
    tags: List[str] = []  # 若你愿意更规范：= Field(default_factory=list)
