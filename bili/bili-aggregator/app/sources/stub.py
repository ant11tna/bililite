import time
from typing import Dict, List

def fetch_creator_videos(uid: int, limit: int) -> List[Dict]:
    now = int(time.time())
    out = []
    for i in range(min(limit, 5)):
        bvid = f"BVSTUB{uid}{i}"
        out.append({
            "bvid": bvid,
            "aid": None,
            "uid": uid,
            "title": f"[stub] uid={uid} video {i}",
            "pub_ts": now - i * 86400,
            "url": f"https://www.bilibili.com/video/{bvid}",
            "cover_url": None,
            "desc": None,
            "tid": None,
            "tname": None,
            "stats": {"view": 1000 + i * 123, "like": 10 + i, "reply": 1},
            "tags": ["stub", "demo"],
        })
    return out
