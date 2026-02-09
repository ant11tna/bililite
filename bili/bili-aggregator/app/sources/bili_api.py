import time
from typing import Dict, List, Optional

import requests
import random


class BiliClient:
    """
    【未经验证】接口可能变更/风控：这里尽量做了容错与降级。
    - 列表接口：拿 bvid/title/pub/stat/分区
    - tag 接口：尽量拿 tag；失败就返回空列表
    """

    def __init__(self, cookie: Optional[str] = None, timeout_sec: int = 15):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
        })
        if cookie:
            # cookie 放原始字符串即可：SESSDATA=...; bili_jct=...; ...
            self.s.headers["Cookie"] = cookie
        self.timeout_sec = timeout_sec

    def _get_json(self, url: str, params: Dict) -> Dict:
        time.sleep(random.uniform(1.0, 2.0))
        r = self.s.get(url, params=params, timeout=self.timeout_sec)
        r.raise_for_status()
        return r.json()


    def fetch_creator_videos(self, uid: int, limit: int) -> List[Dict]:
        """
        【未经验证】常见空间投稿列表接口：
        https://api.bilibili.com/x/space/arc/search?mid={uid}&pn=1&ps={ps}&order=pubdate
        """
        ps = max(1, min(limit, 50))
        url = "https://api.bilibili.com/x/space/arc/search"
        data = self._get_json(url, params={"mid": uid, "pn": 1, "ps": ps, "order": "pubdate"})
        if data.get("code") != 0:
           print("BILI API ERROR:", data.get("code"), data.get("message"), data.get("ttl"))
           return []


        vlist = (((data.get("data") or {}).get("list") or {}).get("vlist")) or []
        out: List[Dict] = []
        now = int(time.time())

        for it in vlist[:limit]:
            bvid = it.get("bvid") or ""
            if not bvid:
                continue

            # 时间字段：pubdate
            pub_ts = int(it.get("pubdate") or now)

            stat = it.get("stat") or {}
            # tid/tname 在 vlist 里通常存在；没有就置空
            tid = it.get("tid")
            tname = it.get("tname")

            aid = it.get("aid")
            tags = []
            if aid:
                tags = []  # 先关掉，等列表稳定后再开

            out.append({
                "bvid": bvid,
                "aid": aid,
                "uid": uid,
                "title": it.get("title") or "",
                "pub_ts": pub_ts,
                "duration_sec": it.get("length"),  # 可能是 "mm:ss" 或秒；后端暂不依赖
                "url": f"https://www.bilibili.com/video/{bvid}",
                "cover_url": it.get("pic"),
                "desc": it.get("description"),
                "tid": tid,
                "tname": tname,
                "stats": {
                    "view": stat.get("view"),
                    "like": stat.get("like"),
                    "reply": stat.get("reply"),
                    "danmaku": stat.get("danmaku"),
                    "favorite": stat.get("favorite"),
                    "coin": stat.get("coin"),
                    "share": stat.get("share"),
                },
                "tags": tags,
            })

        return out

    def fetch_tags_by_aid(self, aid: int) -> List[str]:
        """
        【未经验证】常见稿件 tag 接口之一：
        https://api.bilibili.com/x/tag/archive/tags?aid={aid}
        可能需要登录态/可能被风控；失败则返回 []。
        """
        try:
            url = "https://api.bilibili.com/x/tag/archive/tags"
            data = self._get_json(url, params={"aid": aid})
            if data.get("code") != 0:
                return []
            arr = data.get("data") or []
            tags = []
            for t in arr:
                name = (t.get("tag_name") or "").strip()
                if name:
                    tags.append(name)
            return tags
        except Exception:
            return []
