from fastapi import FastAPI, Query
from typing import List, Optional
import random
import time
from .config import load_config
from .db import connect, init_db
from .schemas import VideoOut, VideoState, VideoStateOut, VideoStateUpdateIn

app = FastAPI()
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app.mount("/static", StaticFiles(directory="web"), name="static")


@app.get("/")
def home():
    return FileResponse("web/index.html")


@app.get("/api/videos", response_model=List[VideoOut])
def list_videos(
    q: Optional[str] = None,
    uid: Optional[int] = None,
    tid: Optional[int] = None,
    tag: Optional[str] = None,
    group: Optional[str] = None,
    view_min: Optional[int] = None,
    view_max: Optional[int] = None,
    state: Optional[VideoState] = None,
    only_whitelist: bool = True,
    sort: str = Query("pub", pattern="^(pub|view)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    cfg = load_config()
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)

    where = []
    params = []

    if q:
        where.append("v.title LIKE ?")
        params.append(f"%{q}%")
    if uid:
        where.append("v.uid=?")
        params.append(uid)
    if tid:
        where.append("v.tid=?")
        params.append(tid)
    if view_min is not None:
        where.append("COALESCE(v.view,0) >= ?")
        params.append(view_min)
    if view_max is not None:
        where.append("COALESCE(v.view,0) <= ?")
        params.append(view_max)
    if tag:
        where.append("EXISTS (SELECT 1 FROM video_tags vt WHERE vt.bvid=v.bvid AND vt.tag=?)")
        params.append(tag)
    if only_whitelist:
        where.append("c.enabled=1")
    if group:
        where.append("c.group_name=?")
        params.append(group)

    if state:
        where.append("COALESCE(s.state, 'NEW')=?")
        params.append(state)
    else:
        where.append("COALESCE(s.state, 'NEW') != 'HIDDEN'")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order_sql = "ORDER BY v.pub_ts DESC" if sort == "pub" else "ORDER BY COALESCE(v.view,0) DESC, v.pub_ts DESC"

    sql = f"""
      SELECT v.bvid, v.uid, v.author_name, v.title, v.pub_ts, v.duration_sec, v.url, v.cover_url, v.tname, v.view,
             COALESCE(s.state, 'NEW') AS state
      FROM videos v
      LEFT JOIN creators c ON c.uid = v.uid
      LEFT JOIN video_state s ON s.bvid = v.bvid
      {where_sql}
      {order_sql}
      LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, (*params, limit, offset)).fetchall()

    out: List[VideoOut] = []
    for r in rows:
        tags = conn.execute("SELECT tag FROM video_tags WHERE bvid=? ORDER BY tag", (r["bvid"],)).fetchall()
        out.append(
            VideoOut(
                bvid=r["bvid"],
                uid=r["uid"],
                author_name=r["author_name"],
                title=r["title"],
                pub_ts=r["pub_ts"],
                duration_sec=r["duration_sec"],
                state=r["state"],
                url=r["url"],
                cover_url=r["cover_url"],
                tname=r["tname"],
                view=r["view"],
                tags=[t["tag"] for t in tags],
            )
        )

    conn.close()
    return out


@app.post("/api/state", response_model=VideoStateOut)
def set_state(payload: VideoStateUpdateIn):
    cfg = load_config()
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)

    updated_ts = int(time.time())
    conn.execute(
        """
        INSERT INTO video_state (bvid, state, updated_ts)
        VALUES (?, ?, ?)
        ON CONFLICT(bvid) DO UPDATE SET
          state=excluded.state,
          updated_ts=excluded.updated_ts
        """,
        (payload.bvid, payload.state, updated_ts),
    )
    conn.commit()
    conn.close()
    return VideoStateOut(bvid=payload.bvid, state=payload.state, updated_ts=updated_ts)


@app.get("/api/state", response_model=List[VideoStateOut])
def list_state(
    bvid: Optional[str] = None,
    state: Optional[VideoState] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    cfg = load_config()
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)

    where = []
    params = []
    if bvid:
        where.append("bvid=?")
        params.append(bvid)
    if state:
        where.append("state=?")
        params.append(state)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    rows = conn.execute(
        f"""
        SELECT bvid, state, updated_ts
        FROM video_state
        {where_sql}
        ORDER BY updated_ts DESC
        LIMIT ? OFFSET ?
        """,
        (*params, limit, offset),
    ).fetchall()
    conn.close()
    return [VideoStateOut(bvid=r["bvid"], state=r["state"], updated_ts=r["updated_ts"]) for r in rows]


@app.get("/api/creator-groups", response_model=List[str])
def list_creator_groups():
    cfg = load_config()
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)
    rows = conn.execute(
        """
        SELECT DISTINCT group_name
        FROM creators
        WHERE group_name IS NOT NULL AND group_name != ''
        ORDER BY group_name
        """
    ).fetchall()
    groups = [r["group_name"] for r in rows]
    conn.close()
    return groups


@app.get("/api/daily", response_model=List[VideoOut])
def list_daily(
    group: Optional[str] = "必看",
    hours: int = Query(24, ge=1, le=168),
    limit: int = Query(50, ge=1, le=200),
    sample: int = Query(5, ge=0, le=200),
):
    cfg = load_config()
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)

    if group:
        row = conn.execute(
            "SELECT 1 FROM creators WHERE enabled=1 AND group_name=? LIMIT 1",
            (group,),
        ).fetchone()
        if not row:
            group = None

    cutoff = int(time.time()) - hours * 3600
    where = ["c.enabled=1", "v.pub_ts >= ?", "COALESCE(s.state, 'NEW') != 'HIDDEN'"]
    params = [cutoff]
    if group:
        where.append("c.group_name=?")
        params.append(group)

    where_sql = "WHERE " + " AND ".join(where)
    sql = f"""
      SELECT v.bvid, v.uid, v.author_name, v.title, v.pub_ts, v.duration_sec, v.url, v.cover_url, v.tname, v.view,
             COALESCE(s.state, 'NEW') AS state
      FROM videos v
      LEFT JOIN creators c ON c.uid = v.uid
      LEFT JOIN video_state s ON s.bvid = v.bvid
      {where_sql}
      ORDER BY v.pub_ts DESC
      LIMIT ?
    """
    rows = conn.execute(sql, (*params, limit)).fetchall()

    out: List[VideoOut] = []
    for r in rows:
        tags = conn.execute("SELECT tag FROM video_tags WHERE bvid=? ORDER BY tag", (r["bvid"],)).fetchall()
        out.append(
            VideoOut(
                bvid=r["bvid"],
                uid=r["uid"],
                author_name=r["author_name"],
                title=r["title"],
                pub_ts=r["pub_ts"],
                duration_sec=r["duration_sec"],
                state=r["state"],
                url=r["url"],
                cover_url=r["cover_url"],
                tname=r["tname"],
                view=r["view"],
                tags=[t["tag"] for t in tags],
            )
        )

    conn.close()
    if sample > 0 and len(out) > sample:
        return random.sample(out, sample)
    return out
