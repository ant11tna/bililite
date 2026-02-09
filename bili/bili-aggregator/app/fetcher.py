import random
import time
from typing import Dict, List, Tuple

from . import db
from .db import connect, init_db


def upsert_creator(conn, uid: int, name: str | None, group_name: str | None, enabled: bool) -> None:
    conn.execute(
        """
        INSERT INTO creators(uid, name, group_name, enabled)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(uid) DO UPDATE SET
          name=excluded.name,
          group_name=excluded.group_name,
          enabled=excluded.enabled
        """,
        (uid, name, group_name, 1 if enabled else 0),
    )

def upsert_video(conn, v: Dict, fetched_ts: int) -> None:
    stats = v.get("stats") or {}
    print("DBG inserting:", v["bvid"], "author_name=", v.get("author_name"), "db=", __file__)
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
           v["bvid"], v.get("aid"), v["uid"], v.get("author_name"), v["title"], v["pub_ts"], v.get("duration_sec"),
           v["url"], v.get("cover_url"), v.get("desc"),
           v.get("tid"), v.get("tname"),
           stats.get("view"), stats.get("like"), stats.get("reply"),
           stats.get("danmaku"), stats.get("favorite"), stats.get("coin"), stats.get("share"),
           fetched_ts, fetched_ts if stats else None
        )

    )

def replace_tags(conn, bvid: str, tags: List[str]) -> None:
    conn.execute("DELETE FROM video_tags WHERE bvid=?", (bvid,))
    for t in tags:
        t2 = (t or "").strip()
        if t2:
            conn.execute("INSERT OR IGNORE INTO video_tags(bvid, tag) VALUES(?,?)", (bvid, t2))

import os
import time
import random
from typing import Dict, Tuple

def run_fetch(config: Dict) -> Tuple[int, int]:
    # === 1. 统一数据库路径，只从 app.db_path 取 ===
    db_path = (config.get("app", {}) or {}).get("db_path", "data/app.db")
    

    # === 2. 建立连接（必须在函数最外层缩进） ===
    conn = db.connect(db_path)
    init_db(conn)

    # === 3. upsert creators ===
    creators = config.get("creators", [])
    for c in creators:
        upsert_creator(
            conn,
            c["uid"],
            c.get("name"),
            c.get("group"),
            bool(c.get("enabled", True))
        )
    conn.commit()

    # === 4. fetch 配置 ===
    source = config["fetch"]["source"]
    print("FETCH SOURCE =", source)
    limit = int(config["fetch"]["per_creator_limit"])
    sleep_min, sleep_max = config["fetch"]["polite_sleep_ms"]

    inserted_or_updated = 0
    creators_rows = conn.execute(
        "SELECT uid FROM creators WHERE enabled=1"
    ).fetchall()

    # === 5. 主抓取循环 ===
    for r in creators_rows:
        uid = int(r["uid"])
        fetched_ts = int(time.time())

        if source == "stub":
            from .sources.stub import fetch_creator_videos
            videos = fetch_creator_videos(uid, limit)

        elif source == "rsshub":
            from .sources.rsshub import fetch_creator_videos
            rss_cfg = config["rsshub"]
            videos = fetch_creator_videos(
                uid, limit, rss_cfg["base_url"], rss_cfg["route_template"]
            )

        elif source == "bili_api":
            from .sources.bili_api import BiliClient
            bcfg = config.get("bilibili", {}) or {}
            client = BiliClient(
                cookie=bcfg.get("cookie"),
                timeout_sec=int(bcfg.get("timeout_sec", 15))
            )
            videos = client.fetch_creator_videos(uid, limit)

        elif source == "bili_dynamic":
            from .sources.bili_dynamic import BiliDynamicWebClient
            bcfg = config.get("bilibili", {}) or {}
            cookie = (bcfg.get("cookie") or "").strip()
            if not cookie:
                raise RuntimeError("bili_dynamic requires bilibili.cookie")

            client = BiliDynamicWebClient(
                cookie=cookie,
                timeout_sec=int(bcfg.get("timeout_sec", 15))
            )
            result = client.fetch_following_videos(limit=limit)
            videos = result["videos"]

        else:
            raise RuntimeError(f"Unknown source: {source}")

        # === 6. 写库 ===
        for v in videos:
            upsert_video(conn, v, fetched_ts)
            replace_tags(conn, v["bvid"], v.get("tags") or [])
            inserted_or_updated += 1

        conn.execute(
            "UPDATE creators SET last_fetch_at=datetime('now') WHERE uid=?",
            (uid,)
        )
        conn.commit()

        time.sleep(
            random.randint(int(sleep_min), int(sleep_max)) / 1000.0
        )

    conn.close()
    return (len(creators_rows), inserted_or_updated)
