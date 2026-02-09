import re
import time
from typing import Dict, List, Optional

import requests


def parse_play_count(s: Optional[str]) -> Optional[int]:
    """
    将 '1234' / '1.2万' / '3.4亿' 等转为整数。
    【未经验证】实际字符串格式可能更多样；这里做常见格式处理。
    """
    if not s:
        return None
    s = str(s).strip().replace(",", "")
    m = re.match(r"^(\d+(?:\.\d+)?)(万|亿)?$", s)
    if not m:
        # 兜底：纯数字提取
        m2 = re.search(r"(\d+)", s)
        return int(m2.group(1)) if m2 else None
    num = float(m.group(1))
    unit = m.group(2)
    if unit == "万":
        num *= 10_000
    elif unit == "亿":
        num *= 100_000_000
    return int(num)


class BiliDynamicWebClient:
    """
    基于 bilibili-API-collect 文档：
    GET https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all
    认证：Cookie (SESSDATA)
    """
    def __init__(self, cookie: str, timeout_sec: int = 15):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.bilibili.com/",
            "Origin": "https://www.bilibili.com",
            "Cookie": cookie or "",
        })
        self.timeout_sec = timeout_sec

    def fetch_following_videos(self, limit: int = 30, offset: Optional[str] = None) -> Dict:
        """
        返回 dict：{"videos": [...], "next_offset": ..., "update_baseline": ...}
        """
        url = "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/all"
        params = {
            "type": "video",          # 只取视频投稿流（文档支持）
            "platform": "web",
        }
        if offset:
            params["offset"] = offset

        r = self.s.get(url, params=params, timeout=self.timeout_sec)
        r.raise_for_status()
        j = r.json()

        if j.get("code") != 0:
            # 直接抛出给上层处理/记录；不要静默吞掉
            raise RuntimeError(f"DYNAMIC_WEB_ERROR code={j.get('code')} msg={j.get('message')}")

        data = j.get("data") or {}
        items = data.get("items") or []

        out: List[Dict] = []
        now = int(time.time())

        for it in items:
            # ✅ 关键：只保留“投稿视频动态”
            if it.get("type") != "DYNAMIC_TYPE_AV":
                continue

            modules = it.get("modules") or {}
            ma = modules.get("module_author") or {}
            md = modules.get("module_dynamic") or {}
            major = md.get("major") or {}
            archive = major.get("archive")

            # 只收录“视频投稿”卡片（archive 存在）
            if not isinstance(archive, dict):
                continue


            bvid = archive.get("bvid")
            aid = archive.get("aid")
            title = archive.get("title") or ""
            cover = archive.get("cover")
            jump_url = archive.get("jump_url") or ""
            desc = archive.get("desc")
            pub_ts = ma.get("pub_ts") or now
            author_name = (ma.get("name") or "").strip()


            mid = ma.get("mid") or "0"
            try:
                uid = int(mid)
            except Exception:
                uid = 0

            # jump_url 可能是 //www...，转成 https
            if jump_url.startswith("//"):
                url_video = "https:" + jump_url
            elif jump_url.startswith("http"):
                url_video = jump_url
            elif bvid:
                url_video = f"https://www.bilibili.com/video/{bvid}"
            else:
                url_video = f"https://www.bilibili.com/video/av{aid}" if aid else None

            if not url_video:
                continue

            stat = archive.get("stat") or {}
            view = parse_play_count(stat.get("play"))

            # bvid 为空时降级主键：避免入库失败（后续可再补）
            pk = bvid or (f"AV{aid}" if aid else f"DYN{uid}{pub_ts}")

            out.append({
                "bvid": pk,
                "aid": int(aid) if aid else None,
                "uid": uid,
                "author_name": author_name,
                "title": title,
                "pub_ts": int(pub_ts),
                "duration_sec": None,
                "url": url_video,
                "cover_url": cover,
                "desc": desc,
                "tid": None,
                "tname": None,
                "stats": {"view": view} if view is not None else {},
                "tags": [],  # 扩展功能：后续再做低频补全
            })

            if len(out) >= limit:
                break

        return {
            "videos": out,
            "next_offset": data.get("offset"),
            "update_baseline": data.get("update_baseline"),
        }
