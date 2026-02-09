from fastapi import FastAPI, Query
from typing import List, Optional
import yaml

from .db import connect, init_db
from .schemas import VideoOut

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

@app.get("/api/videos", response_model=List[VideoOut])
def list_videos(
    q: Optional[str] = None,
    uid: Optional[int] = None,
    tid: Optional[int] = None,
    tag: Optional[str] = None,
    view_min: Optional[int] = None,
    view_max: Optional[int] = None,
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

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order_sql = "ORDER BY v.pub_ts DESC" if sort == "pub" else "ORDER BY COALESCE(v.view,0) DESC, v.pub_ts DESC"

    sql = f"""
      SELECT v.bvid, v.uid, v.author_name, v.title, v.pub_ts, v.url, v.cover_url, v.tname, v.view
      FROM videos v
      {where_sql}
      {order_sql}
      LIMIT ? OFFSET ?
    """
    rows = conn.execute(sql, (*params, limit, offset)).fetchall()
    
    out: List[VideoOut] = []
    for r in rows:
        tags = conn.execute("SELECT tag FROM video_tags WHERE bvid=? ORDER BY tag", (r["bvid"],)).fetchall()
        out.append(VideoOut(
            bvid=r["bvid"],
            uid=r["uid"],
            author_name=r["author_name"],
            title=r["title"],
            pub_ts=r["pub_ts"],
            url=r["url"],
            cover_url=r["cover_url"],
            tname=r["tname"],
            view=r["view"],
            tags=[t["tag"] for t in tags],
        ))

    conn.close()
    return out
