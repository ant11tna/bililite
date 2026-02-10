from fastapi import FastAPI, Query
from typing import List, Optional, Sequence
import random
import time
import yaml

from .db import connect, init_db
from .schemas import CreatorOut, VideoOut, VideoState, VideoStateOut, VideoStateUpdateIn

app = FastAPI()
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app.mount("/static", StaticFiles(directory="web"), name="static")


@app.get("/")
def home():
    return FileResponse("web/index.html")


def load_config() -> dict:
    with open("config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def row_to_video(conn, row) -> VideoOut:
    tags = conn.execute("SELECT tag FROM video_tags WHERE bvid=? ORDER BY tag", (row["bvid"],)).fetchall()
    return VideoOut(
        bvid=row["bvid"],
        uid=row["uid"],
        author_name=row["author_name"],
        title=row["title"],
        pub_ts=row["pub_ts"],
        duration_sec=row["duration_sec"],
        state=row["state"],
        url=row["url"],
        cover_url=row["cover_url"],
        tname=row["tname"],
        view=row["view"],
        tags=[t["tag"] for t in tags],
    )


def weighted_sample_without_replacement(rows: Sequence, k: int):
    pool = list(rows)
    picked = []
    n = min(k, len(pool))
    for _ in range(n):
        total_weight = sum(max(1, int(r["weight"] or 1)) for r in pool)
        ticket = random.uniform(0, total_weight)
        cumsum = 0.0
        index = 0
        for i, row in enumerate(pool):
            cumsum += max(1, int(row["weight"] or 1))
            if ticket <= cumsum:
                index = i
                break
        picked.append(pool.pop(index))
    return picked


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

    out = [row_to_video(conn, r) for r in rows]
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


@app.get("/api/creators", response_model=List[CreatorOut])
def list_creators():
    cfg = load_config()
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)
    rows = conn.execute(
        """
        SELECT uid, name, group_name, priority, weight, last_fetch_at
        FROM creators
        WHERE enabled=1
        ORDER BY priority DESC, uid ASC
        """
    ).fetchall()
    out = [
        CreatorOut(
            uid=r["uid"],
            name=r["name"],
            group=r["group_name"],
            priority=int(r["priority"] or 0),
            weight=max(1, int(r["weight"] or 1)),
            last_fetch_at=r["last_fetch_at"],
        )
        for r in rows
    ]
    conn.close()
    return out


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

    requested_group = group
    group_hit = False
    if group:
        row = conn.execute("SELECT 1 FROM creators WHERE enabled=1 AND group_name=? LIMIT 1", (group,)).fetchone()
        group_hit = bool(row)
        if not group_hit:
            group = None

    cutoff = int(time.time()) - hours * 3600
    base_where = [
        "c.enabled=1",
        "v.pub_ts >= ?",
        "COALESCE(s.state, 'NEW') != 'HIDDEN'",
        "NOT EXISTS (SELECT 1 FROM push_log p WHERE p.bvid=v.bvid)",
    ]
    base_params = [cutoff]
    if group:
        base_where.append("c.group_name=?")
        base_params.append(group)

    where_sql = "WHERE " + " AND ".join(base_where)
    base_sql = f"""
      SELECT v.bvid, v.uid, v.author_name, v.title, v.pub_ts, v.duration_sec, v.url, v.cover_url, v.tname, v.view,
             COALESCE(s.state, 'NEW') AS state,
             c.priority AS priority,
             c.weight AS weight
      FROM videos v
      LEFT JOIN creators c ON c.uid = v.uid
      LEFT JOIN video_state s ON s.bvid = v.bvid
      {where_sql}
      ORDER BY v.pub_ts DESC
    """

    max_items = limit
    dedupe_rows = conn.execute(base_sql, tuple(base_params)).fetchall()

    dropped_by_dedupe = conn.execute(
        """
        SELECT COUNT(1) AS cnt
        FROM videos v
        LEFT JOIN creators c ON c.uid = v.uid
        LEFT JOIN video_state s ON s.bvid = v.bvid
        WHERE c.enabled=1
          AND v.pub_ts >= ?
          AND COALESCE(s.state, 'NEW') != 'HIDDEN'
          AND EXISTS (SELECT 1 FROM push_log p WHERE p.bvid=v.bvid)
          AND (? IS NULL OR c.group_name=?)
        """,
        (cutoff, group, group),
    ).fetchone()["cnt"]

    if group_hit:
        p1 = [r for r in dedupe_rows if int(r["priority"] or 0) == 1]
        p0 = [r for r in dedupe_rows if int(r["priority"] or 0) != 1]
        selected_rows = p1[:max_items]
        if len(selected_rows) < max_items:
            selected_rows.extend(p0[: max_items - len(selected_rows)])
    else:
        p1 = [r for r in dedupe_rows if int(r["priority"] or 0) == 1]
        p0 = [r for r in dedupe_rows if int(r["priority"] or 0) != 1]
        selected_rows = dedupe_rows[:max_items]

    used_sampling = sample > 0 and len(selected_rows) > sample
    if used_sampling:
        selected_rows = weighted_sample_without_replacement(selected_rows, sample)

    out = [row_to_video(conn, r) for r in selected_rows]

    print(
        "[daily]"
        f" requested_group={requested_group!r}"
        f" group_hit={group_hit}"
        f" candidates={len(dedupe_rows)}"
        f" priority1={len(p1)}"
        f" priority0={len(p0)}"
        f" dedupe_dropped={dropped_by_dedupe}"
        f" returned={len(out)}"
        f" sampled={used_sampling}"
    )

    conn.close()
    return out
