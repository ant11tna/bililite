from fastapi import FastAPI, Query
from typing import List, Optional
import random
import time
from .config import load_config
from .db import connect, init_db
from .schemas import (
    CreatorOut,
    CreatorUpdateIn,
    VideoOut,
    VideoState,
    VideoStateOut,
    VideoStateUpdateIn,
)

app = FastAPI()
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app.mount("/static", StaticFiles(directory="web"), name="static")


def _weighted_sample_without_replacement(
    items: List[dict],
    k: int,
    rng: random.Random,
) -> List[dict]:
    """
    Weighted sampling without replacement.
    items: [{"uid": int, "weight": int, ...}, ...]
    """
    if k <= 0 or not items:
        return []

    pool = list(items)
    chosen: List[dict] = []

    while pool and len(chosen) < k:
        total_weight = sum(max(1, int(it.get("weight", 1))) for it in pool)
        pick = rng.uniform(0, total_weight)
        acc = 0.0

        chosen_index = len(pool) - 1
        for idx, it in enumerate(pool):
            acc += max(1, int(it.get("weight", 1)))
            if acc >= pick:
                chosen_index = idx
                break

        chosen.append(pool.pop(chosen_index))

    return chosen


@app.get("/")
def home():
    return FileResponse("web/index.html")




@app.get("/creators")
def creators_page():
    return FileResponse("web/creators.html")

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
        where.append("COALESCE(s.state, 'NEW') NOT IN ('HIDDEN', 'READ')")

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




@app.get("/api/creators", response_model=List[CreatorOut])
def list_creators():
    cfg = load_config()
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)

    rows = conn.execute(
        """
        SELECT uid, COALESCE(author_name, name) AS author_name, enabled, priority, weight
        FROM creators
        ORDER BY uid
        """
    ).fetchall()
    conn.close()

    return [
        CreatorOut(
            uid=r["uid"],
            author_name=r["author_name"],
            enabled=bool(r["enabled"]),
            priority=r["priority"],
            weight=r["weight"],
        )
        for r in rows
    ]


@app.post("/api/creators", response_model=List[CreatorOut])
def update_creators(payload: List[CreatorUpdateIn]):
    cfg = load_config()
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)

    for item in payload:
        current = conn.execute(
            "SELECT uid, enabled, priority, weight FROM creators WHERE uid=?",
            (item.uid,),
        ).fetchone()
        if not current:
            conn.execute(
                """
                INSERT INTO creators(uid, author_name, name, enabled, priority, weight)
                VALUES (?, NULL, NULL, ?, ?, ?)
                """,
                (
                    item.uid,
                    1 if (item.enabled if item.enabled is not None else True) else 0,
                    item.priority if item.priority is not None else 0,
                    max(1, item.weight if item.weight is not None else 1),
                ),
            )
            continue

        enabled = current["enabled"] if item.enabled is None else (1 if item.enabled else 0)
        priority = current["priority"] if item.priority is None else item.priority
        weight = current["weight"] if item.weight is None else max(1, item.weight)

        conn.execute(
            """
            UPDATE creators
            SET enabled=?, priority=?, weight=?
            WHERE uid=?
            """,
            (enabled, priority, weight, item.uid),
        )

    conn.commit()
    rows = conn.execute(
        """
        SELECT uid, COALESCE(author_name, name) AS author_name, enabled, priority, weight
        FROM creators
        ORDER BY uid
        """
    ).fetchall()
    conn.close()

    return [
        CreatorOut(
            uid=r["uid"],
            author_name=r["author_name"],
            enabled=bool(r["enabled"]),
            priority=r["priority"],
            weight=r["weight"],
        )
        for r in rows
    ]

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
    sample: int = Query(1, ge=0, le=200),
    seed: Optional[int] = Query(None),
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
    where = ["c.enabled=1", "v.pub_ts >= ?", "COALESCE(s.state, 'NEW') NOT IN ('HIDDEN', 'READ')"]
    params = [cutoff]
    if group:
        where.append("c.group_name=?")
        params.append(group)

    where_sql = "WHERE " + " AND ".join(where)
    sql = f"""
      SELECT v.bvid, v.uid, v.author_name, v.title, v.pub_ts, v.duration_sec, v.url, v.cover_url, v.tname, v.view,
             COALESCE(s.state, 'NEW') AS state,
             COALESCE(c.priority, 0) AS creator_priority,
             COALESCE(c.weight, 1) AS creator_weight
      FROM videos v
      LEFT JOIN creators c ON c.uid = v.uid
      LEFT JOIN video_state s ON s.bvid = v.bvid
      {where_sql}
      ORDER BY v.pub_ts DESC
      LIMIT 2000
    """
    rows = conn.execute(sql, tuple(params)).fetchall()

    # 每个 creator 仅保留最新一条（creator 粒度）
    latest_by_creator = {}
    for r in rows:
        uid = int(r["uid"])
        if uid not in latest_by_creator:
            latest_by_creator[uid] = r

    latest_rows = list(latest_by_creator.values())

    # Phase 1: 必看 creator（priority > 0），按 priority DESC，再按最新时间
    must_watch_rows = sorted(
        [r for r in latest_rows if int(r["creator_priority"] or 0) > 0],
        key=lambda r: (-int(r["creator_priority"] or 0), -int(r["pub_ts"] or 0)),
    )

    selected_rows = must_watch_rows[:limit]
    if len(selected_rows) >= limit:
        final_rows = selected_rows
    else:
        # Phase 2 候选：普通 creator（priority=0）
        normal_rows = [r for r in latest_rows if int(r["creator_priority"] or 0) <= 0]
        remaining = limit - len(selected_rows)

        if sample == 0:
            # 关闭权重抽样：按时间顺序回退
            normal_rows = sorted(normal_rows, key=lambda r: -int(r["pub_ts"] or 0))
            selected_rows.extend(normal_rows[:remaining])
        else:
            rng = random.Random(seed)
            weighted_pool = [
                {
                    "uid": int(r["uid"]),
                    "weight": max(1, int(r["creator_weight"] or 1)),
                    "row": r,
                }
                for r in normal_rows
            ]
            picked = _weighted_sample_without_replacement(weighted_pool, remaining, rng)
            # 为结果稳定可读，抽样后按发布时间降序展示
            picked_rows = sorted([it["row"] for it in picked], key=lambda r: -int(r["pub_ts"] or 0))
            selected_rows.extend(picked_rows)

        final_rows = selected_rows[:limit]

    out: List[VideoOut] = []
    for r in final_rows:
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
