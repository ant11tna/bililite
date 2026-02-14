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


class StatsTnameCount(BaseModel):
    tname: str
    cnt: int


class StatsCreatorCount(BaseModel):
    uid: int
    author_name: Optional[str] = None
    cnt: int


class StatsOverviewOut(BaseModel):
    window_days: int
    total_creators: int
    enabled_creators: int
    priority_creators: int
    videos_in_window: int
    pushed_in_window: int
    distinct_creators_pushed: int
    top_tnames_pushed: List[StatsTnameCount] = []
    top_creators_pushed: List[StatsCreatorCount] = []
    note: str = ""


class CreatorTnameMix(BaseModel):
    tname: str
    cnt: int


class CreatorStatsOut(BaseModel):
    uid: int
    author_name: Optional[str] = None
    enabled: bool
    priority: int = 0
    weight: int = 1
    last_pub_ts: Optional[int] = None
    last_pushed_ts: Optional[int] = None
    pushed_count: int = 0
    pushed_bvids_sample: List[str] = []
    pushed_tname_mix: List[CreatorTnameMix] = []
    hidden_count_window: int = 0
    read_count_window: int = 0
    hidden_count_all_time: int = 0
    read_count_all_time: int = 0
    freshness_hours: Optional[float] = None
    suppression_hint: str = ""
    note: str = ""
