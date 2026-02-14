from fastapi import FastAPI, Query
from typing import List, Optional
import random
import time
from .config import load_config
from .db import connect, init_db
from .schemas import (
    CreatorOut,
    CreatorStatsOut,
    CreatorTnameMix,
    StatsCreatorCount,
    StatsOverviewOut,
    StatsTnameCount,
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


@app.get("/stats")
def stats_page():
    return FileResponse("web/stats.html")


def _has_video_state_updated_ts(conn) -> bool:
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(video_state)").fetchall()
    }
    return "updated_ts" in cols


@app.get("/api/stats/overview", response_model=StatsOverviewOut)
def stats_overview(
    days: int = Query(7, ge=1, le=3650),
    channel: str = Query("serverchan"),
):
    cfg = load_config()
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)

    cutoff = int(time.time()) - days * 86400
    note_parts: List[str] = []

    total_creators = int(conn.execute("SELECT COUNT(*) AS c FROM creators").fetchone()["c"] or 0)
    enabled_creators = int(conn.execute("SELECT COUNT(*) AS c FROM creators WHERE enabled=1").fetchone()["c"] or 0)
    priority_creators = int(conn.execute("SELECT COUNT(*) AS c FROM creators WHERE priority>0").fetchone()["c"] or 0)

    videos_in_window = int(
        conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM videos v
            LEFT JOIN video_state hs ON hs.bvid=v.bvid AND hs.state='HIDDEN'
            WHERE hs.bvid IS NULL
              AND v.pub_ts >= ?
            """,
            (cutoff,),
        ).fetchone()["c"]
        or 0
    )

    pushed_in_window = int(
        conn.execute(
            "SELECT COUNT(*) AS c FROM push_log WHERE channel=? AND pushed_ts>=?",
            (channel, cutoff),
        ).fetchone()["c"]
        or 0
    )

    distinct_creators_pushed = int(
        conn.execute(
            """
            SELECT COUNT(DISTINCT v.uid) AS c
            FROM push_log pl
            JOIN videos v ON v.bvid=pl.bvid
            WHERE pl.channel=?
              AND pl.pushed_ts>=?
            """,
            (channel, cutoff),
        ).fetchone()["c"]
        or 0
    )

    top_tname_rows = conn.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(v.tname),''), '未分区') AS tname, COUNT(*) AS cnt
        FROM push_log pl
        JOIN videos v ON v.bvid=pl.bvid
        WHERE pl.channel=?
          AND pl.pushed_ts>=?
        GROUP BY COALESCE(NULLIF(TRIM(v.tname),''), '未分区')
        ORDER BY cnt DESC, tname ASC
        LIMIT 5
        """,
        (channel, cutoff),
    ).fetchall()
    top_tnames_pushed = [StatsTnameCount(tname=r["tname"], cnt=int(r["cnt"] or 0)) for r in top_tname_rows]

    top_creator_rows = conn.execute(
        """
        SELECT v.uid AS uid, COALESCE(c.author_name, c.name, v.author_name) AS author_name, COUNT(*) AS cnt
        FROM push_log pl
        JOIN videos v ON v.bvid=pl.bvid
        LEFT JOIN creators c ON c.uid=v.uid
        WHERE pl.channel=?
          AND pl.pushed_ts>=?
        GROUP BY v.uid, COALESCE(c.author_name, c.name, v.author_name)
        ORDER BY cnt DESC, v.uid ASC
        LIMIT 10
        """,
        (channel, cutoff),
    ).fetchall()
    top_creators_pushed = [
        StatsCreatorCount(uid=int(r["uid"]), author_name=r["author_name"], cnt=int(r["cnt"] or 0))
        for r in top_creator_rows
    ]

    if not _has_video_state_updated_ts(conn):
        note_parts.append("video_state 无 updated_ts，read/hidden 时间窗统计将退化为全量")

    conn.close()
    return StatsOverviewOut(
        window_days=days,
        total_creators=total_creators,
        enabled_creators=enabled_creators,
        priority_creators=priority_creators,
        videos_in_window=videos_in_window,
        pushed_in_window=pushed_in_window,
        distinct_creators_pushed=distinct_creators_pushed,
        top_tnames_pushed=top_tnames_pushed,
        top_creators_pushed=top_creators_pushed,
        note="; ".join(note_parts),
    )


@app.get("/api/stats/creators", response_model=List[CreatorStatsOut])
def list_creator_stats(
    days: int = Query(30, ge=1, le=3650),
    channel: str = Query("serverchan"),
    limit: int = Query(200, ge=1, le=2000),
):
    cfg = load_config()
    conn = connect(cfg["app"]["db_path"])
    init_db(conn)

    cutoff = int(time.time()) - days * 86400
    has_updated_ts = _has_video_state_updated_ts(conn)
    note = ""

    base_rows = conn.execute(
        """
        SELECT
          c.uid AS uid,
          COALESCE(c.author_name, c.name) AS author_name,
          c.enabled AS enabled,
          COALESCE(c.priority,0) AS priority,
          COALESCE(c.weight,1) AS weight,
          p.pushed_count AS pushed_count,
          p.last_pushed_ts AS last_pushed_ts,
          vp.last_pub_ts AS last_pub_ts
        FROM creators c
        LEFT JOIN (
            SELECT v.uid AS uid, COUNT(*) AS pushed_count, MAX(pl.pushed_ts) AS last_pushed_ts
            FROM push_log pl
            JOIN videos v ON v.bvid=pl.bvid
            WHERE pl.channel=?
              AND pl.pushed_ts>=?
            GROUP BY v.uid
        ) p ON p.uid = c.uid
        LEFT JOIN (
            SELECT v.uid AS uid, MAX(v.pub_ts) AS last_pub_ts
            FROM videos v
            LEFT JOIN video_state hs ON hs.bvid=v.bvid AND hs.state='HIDDEN'
            WHERE hs.bvid IS NULL
            GROUP BY v.uid
        ) vp ON vp.uid = c.uid
        ORDER BY COALESCE(c.priority,0) DESC,
                 c.enabled DESC,
                 COALESCE(p.pushed_count,0) DESC,
                 COALESCE(vp.last_pub_ts,0) DESC,
                 c.uid ASC
        LIMIT ?
        """,
        (channel, cutoff, limit),
    ).fetchall()

    uid_rows = [int(r["uid"]) for r in base_rows]

    sample_map = {}
    mix_map = {}
    hidden_map = {}
    read_map = {}

    if uid_rows:
        uid_placeholders = ",".join(["?"] * len(uid_rows))

        sample_rows = conn.execute(
            f"""
            SELECT x.uid, x.bvid
            FROM (
                SELECT v.uid AS uid, pl.bvid AS bvid, pl.pushed_ts AS pushed_ts,
                       ROW_NUMBER() OVER (PARTITION BY v.uid ORDER BY pl.pushed_ts DESC, pl.bvid ASC) AS rn
                FROM push_log pl
                JOIN videos v ON v.bvid=pl.bvid
                WHERE pl.channel=?
                  AND pl.pushed_ts>=?
                  AND v.uid IN ({uid_placeholders})
            ) x
            WHERE x.rn<=3
            ORDER BY x.uid ASC, x.rn ASC
            """,
            (channel, cutoff, *uid_rows),
        ).fetchall()
        for r in sample_rows:
            sample_map.setdefault(int(r["uid"]), []).append(r["bvid"])

        mix_rows = conn.execute(
            f"""
            SELECT y.uid, y.tname, y.cnt
            FROM (
                SELECT v.uid AS uid,
                       COALESCE(NULLIF(TRIM(v.tname),''), '未分区') AS tname,
                       COUNT(*) AS cnt,
                       ROW_NUMBER() OVER (
                           PARTITION BY v.uid
                           ORDER BY COUNT(*) DESC, COALESCE(NULLIF(TRIM(v.tname),''), '未分区') ASC
                       ) AS rn
                FROM push_log pl
                JOIN videos v ON v.bvid=pl.bvid
                WHERE pl.channel=?
                  AND pl.pushed_ts>=?
                  AND v.uid IN ({uid_placeholders})
                GROUP BY v.uid, COALESCE(NULLIF(TRIM(v.tname),''), '未分区')
            ) y
            WHERE y.rn<=3
            ORDER BY y.uid ASC, y.cnt DESC, y.tname ASC
            """,
            (channel, cutoff, *uid_rows),
        ).fetchall()
        for r in mix_rows:
            mix_map.setdefault(int(r["uid"]), []).append(CreatorTnameMix(tname=r["tname"], cnt=int(r["cnt"] or 0)))

        if has_updated_ts:
            state_rows = conn.execute(
                f"""
                SELECT v.uid AS uid,
                       SUM(CASE WHEN s.state='HIDDEN' THEN 1 ELSE 0 END) AS hidden_cnt,
                       SUM(CASE WHEN s.state='READ' THEN 1 ELSE 0 END) AS read_cnt
                FROM video_state s
                JOIN videos v ON v.bvid=s.bvid
                WHERE s.updated_ts>=?
                  AND v.uid IN ({uid_placeholders})
                GROUP BY v.uid
                """,
                (cutoff, *uid_rows),
            ).fetchall()
        else:
            note = "video_state 无时间字段，read/hidden 使用 all_time 统计"
            state_rows = conn.execute(
                f"""
                SELECT v.uid AS uid,
                       SUM(CASE WHEN s.state='HIDDEN' THEN 1 ELSE 0 END) AS hidden_cnt,
                       SUM(CASE WHEN s.state='READ' THEN 1 ELSE 0 END) AS read_cnt
                FROM video_state s
                JOIN videos v ON v.bvid=s.bvid
                WHERE v.uid IN ({uid_placeholders})
                GROUP BY v.uid
                """,
                tuple(uid_rows),
            ).fetchall()

        for r in state_rows:
            uid = int(r["uid"])
            hidden_map[uid] = int(r["hidden_cnt"] or 0)
            read_map[uid] = int(r["read_cnt"] or 0)

    now_ts = int(time.time())
    window_start = now_ts - days * 86400

    out: List[CreatorStatsOut] = []
    for r in base_rows:
        uid = int(r["uid"])
        pushed_count = int(r["pushed_count"] or 0)
        last_pub_ts = r["last_pub_ts"]
        freshness_hours = None
        if last_pub_ts is not None:
            freshness_hours = round((now_ts - int(last_pub_ts)) / 3600.0, 1)

        has_new_video_in_window = last_pub_ts is not None and int(last_pub_ts) >= window_start
        enabled = bool(r["enabled"])
        priority = int(r["priority"] or 0)

        if not enabled:
            suppression_hint = "enabled=false"
        elif pushed_count == 0 and has_new_video_in_window and priority > 0:
            suppression_hint = f"priority>0 但近{days}天未推送(检查 cooldown/tname cap)"
        elif pushed_count == 0 and has_new_video_in_window:
            suppression_hint = f"近{days}天未推送但有新视频"
        elif last_pub_ts is None:
            suppression_hint = "暂无可见视频"
        else:
            suppression_hint = ""

        hidden_window = hidden_map.get(uid, 0) if has_updated_ts else 0
        read_window = read_map.get(uid, 0) if has_updated_ts else 0
        hidden_all = hidden_map.get(uid, 0) if not has_updated_ts else 0
        read_all = read_map.get(uid, 0) if not has_updated_ts else 0

        out.append(
            CreatorStatsOut(
                uid=uid,
                author_name=r["author_name"],
                enabled=enabled,
                priority=priority,
                weight=max(1, int(r["weight"] or 1)),
                last_pub_ts=last_pub_ts,
                last_pushed_ts=r["last_pushed_ts"],
                pushed_count=pushed_count,
                pushed_bvids_sample=sample_map.get(uid, []),
                pushed_tname_mix=mix_map.get(uid, []),
                hidden_count_window=hidden_window,
                read_count_window=read_window,
                hidden_count_all_time=hidden_all,
                read_count_all_time=read_all,
                freshness_hours=freshness_hours,
                suppression_hint=suppression_hint,
                note=note,
            )
        )

    conn.close()
    return out
