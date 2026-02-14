import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterable, List, Optional

from . import db
from .main import list_daily

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
UNKNOWN_TNAME = "(unknown)"


def format_view(view: Optional[int]) -> str:
    if view is None:
        return "-"
    if view < 10000:
        return str(view)
    if view < 100000000:
        return f"{view / 10000:.1f}万"
    return f"{view / 100000000:.1f}亿"


def time_ago(ts: int) -> str:
    diff = int(time.time()) - ts
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{diff // 60}分钟前"
    if diff < 86400:
        return f"{diff // 3600}小时前"
    if diff < 86400 * 7:
        return f"{diff // 86400}天前"
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def format_author(author_name: Optional[str], uid: int) -> str:
    return author_name or f"uid={uid}"


def format_tname(tname: Optional[str]) -> str:
    if tname:
        return tname
    return "未分区"


def truncate_title(title: str, limit: int = 60) -> str:
    if len(title) <= limit:
        return title
    return title[:limit].rstrip() + "…"


def build_daily_url(base_url: str, params: Dict[str, Any]) -> str:
    query = urllib.parse.urlencode(params)
    return f"{base_url}/api/daily?{query}"


def fetch_daily_via_http(base_url: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    url = build_daily_url(base_url, params)
    with urllib.request.urlopen(url, timeout=5) as resp:
        payload = resp.read().decode("utf-8")
    return json.loads(payload)


def fetch_daily_via_db(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    videos = list_daily(
        group=params.get("group"),
        hours=params.get("hours", 24),
        limit=params.get("limit", 50),
        sample=params.get("sample", 5),
    )
    out: List[Dict[str, Any]] = []
    for v in videos:
        if hasattr(v, "model_dump"):
            out.append(v.model_dump())
        else:
            out.append(v.dict())
    return out


def fetch_daily_candidates(config: dict) -> List[Dict[str, Any]]:
    daily_cfg = (config.get("push") or {}).get("daily") or {}
    group = daily_cfg.get("group", "必看")
    if not group:
        group = None
    params = {
        "group": group,
        "hours": int(daily_cfg.get("hours", 24)),
        "limit": int(daily_cfg.get("limit", 50)),
        "sample": int(daily_cfg.get("sample", 5)),
    }
    params = {k: v for k, v in params.items() if v is not None}

    base_url = (config.get("app") or {}).get("base_url") or DEFAULT_BASE_URL
    try:
        return fetch_daily_via_http(base_url, params)
    except Exception:
        return fetch_daily_via_db(params)


def filter_push_log(conn, channel: str, videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not videos:
        return []
    bvids = [v.get("bvid") for v in videos if v.get("bvid")]
    if not bvids:
        return []
    placeholders = ",".join(["?"] * len(bvids))
    rows = conn.execute(
        f"SELECT bvid FROM push_log WHERE channel=? AND bvid IN ({placeholders})",
        (channel, *bvids),
    ).fetchall()
    pushed = {r["bvid"] for r in rows}
    return [v for v in videos if v.get("bvid") not in pushed]


def apply_max_items(videos: List[Dict[str, Any]], max_items: int) -> List[Dict[str, Any]]:
    if max_items <= 0:
        return videos
    return videos[:max_items]


def write_push_log(conn, channel: str, videos: List[Dict[str, Any]]) -> int:
    if not videos:
        return 0
    now = int(time.time())
    inserted = 0
    for v in videos:
        bvid = v.get("bvid")
        if not bvid:
            continue
        result = conn.execute(
            "INSERT OR IGNORE INTO push_log(bvid, channel, pushed_ts) VALUES(?,?,?)",
            (bvid, channel, now),
        )
        if result.rowcount:
            inserted += result.rowcount
    conn.commit()
    return inserted


def fetch_video_meta_map(conn, bvids: List[str]) -> Dict[str, Dict[str, Any]]:
    if not bvids:
        return {}
    placeholders = ",".join(["?"] * len(bvids))
    rows = conn.execute(
        f"""
        SELECT bvid, uid, tname, view, title, author_name, pub_ts, url
        FROM videos
        WHERE bvid IN ({placeholders})
        """,
        tuple(bvids),
    ).fetchall()
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        out[r["bvid"]] = {
            "uid": r["uid"],
            "tname": r["tname"],
            "view": r["view"],
            "title": r["title"],
            "author_name": r["author_name"],
            "pub_ts": r["pub_ts"],
            "url": r["url"],
        }
    return out


def enrich_candidates_with_db(conn, videos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bvids = [v.get("bvid") for v in videos if v.get("bvid")]
    meta_map = fetch_video_meta_map(conn, bvids)
    out: List[Dict[str, Any]] = []
    for v in videos:
        bvid = v.get("bvid")
        if not bvid:
            continue
        meta = meta_map.get(bvid, {})
        merged = dict(v)
        for key in ("uid", "tname", "view", "title", "author_name", "pub_ts", "url"):
            if merged.get(key) is None and meta.get(key) is not None:
                merged[key] = meta[key]
        out.append(merged)
    return out


def load_recent_pushed_uid_set(conn, channel: str, cooldown_hours: int, now_ts: int) -> set[int]:
    if cooldown_hours <= 0:
        return set()
    cutoff = now_ts - cooldown_hours * 3600
    rows = conn.execute(
        """
        SELECT DISTINCT v.uid AS uid
        FROM push_log pl
        JOIN videos v ON v.bvid = pl.bvid
        WHERE pl.channel = ?
          AND pl.pushed_ts >= ?
        """,
        (channel, cutoff),
    ).fetchall()
    return {int(r["uid"]) for r in rows if r["uid"] is not None}


def apply_throttle_filters(
    conn,
    channel: str,
    videos: List[Dict[str, Any]],
    throttle_cfg: Dict[str, Any],
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    now_ts = int(time.time())
    creator_cooldown_hours = max(0, int(throttle_cfg.get("creator_cooldown_hours", 0) or 0))
    min_view = max(0, int(throttle_cfg.get("min_view", 0) or 0))
    tname_max_per_push = max(0, int(throttle_cfg.get("tname_max_per_push", 0) or 0))

    # (a) creator cooldown
    drop_creator_cooldown = 0
    cooldown_uids = load_recent_pushed_uid_set(conn, channel, creator_cooldown_hours, now_ts)
    stage_a: List[Dict[str, Any]] = []
    for v in videos:
        uid = v.get("uid")
        try:
            uid_int = int(uid) if uid is not None else None
        except Exception:
            uid_int = None
        if cooldown_uids and uid_int is not None and uid_int in cooldown_uids:
            drop_creator_cooldown += 1
            continue
        stage_a.append(v)

    # (b) min view
    drop_min_view = 0
    stage_b: List[Dict[str, Any]] = []
    for v in stage_a:
        if min_view <= 0:
            stage_b.append(v)
            continue
        view = v.get("view")
        # 缺失播放量时保守放行，避免误伤新稿
        if view is None:
            stage_b.append(v)
            continue
        try:
            view_int = int(view)
        except Exception:
            stage_b.append(v)
            continue
        if view_int < min_view:
            drop_min_view += 1
            continue
        stage_b.append(v)

    # (c) tname cap（按出现顺序保留）
    drop_tname_cap = 0
    stage_c: List[Dict[str, Any]] = []
    tname_counter: Dict[str, int] = {}
    for v in stage_b:
        if tname_max_per_push <= 0:
            stage_c.append(v)
            continue
        tname = (v.get("tname") or "").strip() or UNKNOWN_TNAME
        current = tname_counter.get(tname, 0)
        if current >= tname_max_per_push:
            drop_tname_cap += 1
            continue
        tname_counter[tname] = current + 1
        stage_c.append(v)

    return stage_c, {
        "candidates": len(videos),
        "drop_creator_cooldown": drop_creator_cooldown,
        "drop_min_view": drop_min_view,
        "drop_tname_cap": drop_tname_cap,
        "final": len(stage_c),
    }


def build_markdown(videos: Iterable[Dict[str, Any]], home_url: str) -> str:
    lines = []
    for v in videos:
        author = format_author(v.get("author_name"), v.get("uid"))
        view = format_view(v.get("view"))
        ago = time_ago(v.get("pub_ts", int(time.time())))
        tname = format_tname(v.get("tname"))
        title = truncate_title(v.get("title", ""))
        url = v.get("url", "")
        lines.append(
            f"- 作者：{author} | 标题：{title} | 播放：{view} | 时间：{ago} | 分区：{tname} | 链接：{url}"
        )
    if not lines:
        return "（暂无内容）"
    lines.append(f"\nhome_url: {home_url}")
    return "\n".join(lines)


def post_serverchan(sendkey: str, title: str, desp: str) -> int:
    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    data = urllib.parse.urlencode({"title": title, "desp": desp}).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        for token in reason.split():
            if token.isdigit() and len(token) == 3:
                return int(token)
        return 0


def build_daily_message(config: dict) -> Dict[str, Any]:
    push_cfg = config.get("push") or {}
    videos = fetch_daily_candidates(config)
    today = time.strftime("%Y-%m-%d", time.localtime())
    if not videos:
        title = f"Bililite · 今日必看（0条）· {today}"
        content = "\n".join(
            [
                "**今日必看（0条）**",
                "无新内容（均已推送或窗口内无新视频）",
                "打开 Bililite：http://127.0.0.1:9000/",
            ]
        )
        return {"title": title, "content": content, "videos": []}

    conn = db.connect((config.get("app") or {}).get("db_path", "data/app.db"))
    db.init_db(conn)
    channel = push_cfg.get("provider", "serverchan")

    before_dedup = len(videos)
    videos = filter_push_log(conn, channel, videos)
    drop_push_log_dedup = before_dedup - len(videos)

    # 由本地 DB 回查并补齐推送字段，避免依赖 /api/daily 返回字段完整度
    videos = enrich_candidates_with_db(conn, videos)

    throttle_cfg = (push_cfg.get("throttle") or {})
    videos, stats = apply_throttle_filters(conn, channel, videos, throttle_cfg)

    max_items = int(((push_cfg.get("daily") or {}).get("max_items") or 0))
    videos = apply_max_items(videos, max_items)
    conn.close()

    print(
        "push_throttle_stats: "
        f"candidates={stats['candidates']}, "
        f"drop_push_log_dedup={drop_push_log_dedup}, "
        f"drop_creator_cooldown={stats['drop_creator_cooldown']}, "
        f"drop_min_view={stats['drop_min_view']}, "
        f"drop_tname_cap={stats['drop_tname_cap']}, "
        f"final={len(videos)}"
    )

    if not videos:
        title = f"Bililite · 今日必看（0条）· {today}"
        content = "\n".join(
            [
                "**今日必看（0条）**",
                "无新内容（均已推送或窗口内无新视频）",
                "打开 Bililite：http://127.0.0.1:9000/",
            ]
        )
        return {"title": title, "content": content, "videos": []}

    title = f"Bililite · 今日必看（{len(videos)}条）· {today}"
    base_url = (config.get("app") or {}).get("base_url") or DEFAULT_BASE_URL
    content = build_markdown(videos, f"{base_url}/")
    return {"title": title, "content": content, "videos": videos}


def send_daily_push(config: dict) -> int:
    push_cfg = config.get("push") or {}
    if not push_cfg.get("enabled", False):
        print("push.enabled=false, skip")
        return 0

    provider = push_cfg.get("provider", "serverchan")
    if provider != "serverchan":
        print(f"Unsupported push provider: {provider}")
        return 1

    message = build_daily_message(config)
    videos = message.get("videos") or []
    if not videos:
        print("无新内容，跳过发送")
        return 0

    sendkey = ((push_cfg.get("serverchan") or {}).get("sendkey") or "").strip()
    if not sendkey:
        print("push.serverchan.sendkey 未配置，请在 config.yaml 设置后重试")
        return 1

    title = message["title"]
    content = message["content"]
    print(content)
    status = post_serverchan(sendkey, title, content)
    print(f"Server酱响应状态码: {status}")
    if status < 200 or status >= 300:
        print("推送失败，未写入去重记录")
        return 1

    conn = db.connect((config.get("app") or {}).get("db_path", "data/app.db"))
    db.init_db(conn)
    inserted = write_push_log(conn, provider, videos)
    print(f"push_log 写入成功：{inserted} 条")
    conn.close()
    return 0
