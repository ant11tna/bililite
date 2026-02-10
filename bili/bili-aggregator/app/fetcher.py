import random
import time
from typing import Dict, List, Tuple

from . import db
from .db import init_db


def upsert_creator(
    conn,
    uid: int,
    name: str | None,
    group_name: str | None,
    enabled: bool,
    priority: int = 0,
    weight: int = 100,
) -> None:
    normalized_priority = 1 if int(priority or 0) > 0 else 0
    normalized_weight = max(1, int(weight or 100))
    conn.execute(
        """
        INSERT INTO creators(uid, name, group_name, priority, weight, enabled)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(uid) DO UPDATE SET
          name=excluded.name,
          group_name=excluded.group_name,
          priority=excluded.priority,
          weight=excluded.weight,
          enabled=excluded.enabled
        """,
        (uid, name, group_name, normalized_priority, normalized_weight, 1 if enabled else 0),
    )


def upsert_video(conn, v: Dict, fetched_ts: int) -> None:
    stats = v.get("stats") or {}
    conn.execute(
        """
        INSERT INTO videos(
          bvid, aid, uid, author_name, title, pub_ts, duration_sec, url, cover_url, "desc",
          tid, tname,
          view, like_cnt, reply_cnt, danmaku, favorite, coin, share,
          fetched_ts, stats_ts
        )
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(bvid) DO UPDATE SET
          author_name=COALESCE(excluded.author_name, videos.author_name),
          title=excluded.title,
          pub_ts=excluded.pub_ts,
          url=excluded.url,
          cover_url=excluded.cover_url,
          "desc"=excluded."desc",
          tid=excluded.tid,
          tname=excluded.tname,
          view=COALESCE(excluded.view, videos.view),
          like_cnt=COALESCE(excluded.like_cnt, videos.like_cnt),
          reply_cnt=COALESCE(excluded.reply_cnt, videos.reply_cnt),
          fetched_ts=excluded.fetched_ts,
          stats_ts=COALESCE(excluded.stats_ts, videos.stats_ts)
        """,
        (
            v["bvid"],
            v.get("aid"),
            v["uid"],
            v.get("author_name"),
            v["title"],
            v["pub_ts"],
            v.get("duration_sec"),
            v["url"],
            v.get("cover_url"),
            v.get("desc"),
            v.get("tid"),
            v.get("tname"),
            stats.get("view"),
            stats.get("like"),
            stats.get("reply"),
            stats.get("danmaku"),
            stats.get("favorite"),
            stats.get("coin"),
            stats.get("share"),
            fetched_ts,
            fetched_ts if stats else None,
        ),
    )


def replace_tags(conn, bvid: str, tags: List[str]) -> None:
    conn.execute("DELETE FROM video_tags WHERE bvid=?", (bvid,))
    for t in tags:
        t2 = (t or "").strip()
        if t2:
            conn.execute("INSERT OR IGNORE INTO video_tags(bvid, tag) VALUES(?,?)", (bvid, t2))


def run_fetch(config: Dict) -> Tuple[int, int]:
    db_path = (config.get("app", {}) or {}).get("db_path", "data/app.db")
    conn = db.connect(db_path)
    init_db(conn)

    creators = config.get("creators", [])
    for c in creators:
        upsert_creator(
            conn,
            c["uid"],
            c.get("name"),
            c.get("group"),
            bool(c.get("enabled", True)),
            int(c.get("priority", 0)),
            int(c.get("weight", 100)),
        )
    conn.commit()

    source = config["fetch"]["source"]
    print("FETCH SOURCE =", source)
    limit = int(config["fetch"]["per_creator_limit"])
    sleep_min, sleep_max = config["fetch"]["polite_sleep_ms"]

    inserted_or_updated = 0
    creators_rows = conn.execute("SELECT uid FROM creators WHERE enabled=1").fetchall()

    for r in creators_rows:
        uid = int(r["uid"])
        fetched_ts = int(time.time())

        if source == "stub":
            from .sources.stub import fetch_creator_videos

            videos = fetch_creator_videos(uid, limit)

        elif source == "rsshub":
            from .sources.rsshub import fetch_creator_videos

            rss_cfg = config["rsshub"]
            videos = fetch_creator_videos(uid, limit, rss_cfg["base_url"], rss_cfg["route_template"])

        elif source == "bili_api":
            from .sources.bili_api import BiliClient

            bcfg = config.get("bilibili", {}) or {}
            client = BiliClient(cookie=bcfg.get("cookie"), timeout_sec=int(bcfg.get("timeout_sec", 15)))
            videos = client.fetch_creator_videos(uid, limit)

        elif source == "bili_dynamic":
            from .sources.bili_dynamic import BiliDynamicWebClient

            bcfg = config.get("bilibili", {}) or {}
            cookie = (bcfg.get("cookie") or "").strip()
            if not cookie:
                raise RuntimeError("bili_dynamic requires bilibili.cookie")

            client = BiliDynamicWebClient(cookie=cookie, timeout_sec=int(bcfg.get("timeout_sec", 15)))
            result = client.fetch_following_videos(limit=limit)
            videos = result["videos"]

        else:
            raise RuntimeError(f"Unknown source: {source}")

        for v in videos:
            upsert_video(conn, v, fetched_ts)
            replace_tags(conn, v["bvid"], v.get("tags") or [])
            inserted_or_updated += 1

        conn.execute("UPDATE creators SET last_fetch_at=datetime('now') WHERE uid=?", (uid,))
        conn.commit()

        time.sleep(random.randint(int(sleep_min), int(sleep_max)) / 1000.0)

    conn.close()
    return (len(creators_rows), inserted_or_updated)
