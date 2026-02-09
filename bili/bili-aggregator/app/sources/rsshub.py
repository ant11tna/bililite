import feedparser
import time
from typing import Dict, List
from urllib.parse import urljoin

def fetch_creator_videos(uid: int, limit: int, base_url: str, route_template: str) -> List[Dict]:
    route = route_template.format(uid=uid)
    feed_url = urljoin(base_url.rstrip("/") + "/", route.lstrip("/"))
    feed = feedparser.parse(feed_url)

    out: List[Dict] = []
    for e in feed.entries[:limit]:
        link = getattr(e, "link", None) or ""
        title = getattr(e, "title", "") or ""
        published_parsed = getattr(e, "published_parsed", None)

        if published_parsed:
            pub_ts = int(time.mktime(published_parsed))
        else:
            pub_ts = int(time.time())

        # bvid：RSS 不一定能直接提供；这里用 link 做降级主键（仍可能重复）
        bvid = link.split("/")[-1] if link else f"RSS{uid}{pub_ts}"

        out.append({
            "bvid": bvid,
            "aid": None,
            "uid": uid,
            "title": title,
            "pub_ts": pub_ts,
            "url": link,
            "cover_url": None,
            "desc": getattr(e, "summary", None),
            "tid": None,
            "tname": None,
            "stats": {},
            "tags": [],
        })
    return out
