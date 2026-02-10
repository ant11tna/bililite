import os
import sqlite3
from pathlib import Path

DDL = r"""
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS creators (
  uid INTEGER PRIMARY KEY,
  name TEXT,
  group_name TEXT,
  priority INTEGER NOT NULL DEFAULT 0,
  weight INTEGER NOT NULL DEFAULT 100,
  enabled INTEGER NOT NULL DEFAULT 1,
  last_fetch_at TEXT
);

CREATE TABLE IF NOT EXISTS videos (
  bvid TEXT PRIMARY KEY,
  aid INTEGER,
  uid INTEGER NOT NULL,
  title TEXT NOT NULL,
  pub_ts INTEGER NOT NULL,
  duration_sec INTEGER,
  url TEXT NOT NULL,
  cover_url TEXT,
  "desc" TEXT,
  tid INTEGER,
  tname TEXT,
  view INTEGER,
  like_cnt INTEGER,
  reply_cnt INTEGER,
  danmaku INTEGER,
  favorite INTEGER,
  coin INTEGER,
  share INTEGER,
  author_name TEXT,
  fetched_ts INTEGER NOT NULL,
  stats_ts INTEGER
);

CREATE INDEX IF NOT EXISTS idx_creators_enabled ON creators(enabled);
CREATE INDEX IF NOT EXISTS idx_videos_uid_pub ON videos(uid, pub_ts DESC);
CREATE INDEX IF NOT EXISTS idx_videos_pub ON videos(pub_ts DESC);
CREATE INDEX IF NOT EXISTS idx_videos_tid ON videos(tid);
CREATE INDEX IF NOT EXISTS idx_videos_view ON videos(view);

CREATE TABLE IF NOT EXISTS video_tags (
  bvid TEXT NOT NULL,
  tag TEXT NOT NULL,
  PRIMARY KEY(bvid, tag)
);

CREATE INDEX IF NOT EXISTS idx_video_tags_tag ON video_tags(tag);


CREATE TABLE IF NOT EXISTS video_state (
  bvid TEXT PRIMARY KEY,
  state TEXT NOT NULL,
  updated_ts INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_video_state_state ON video_state(state);

CREATE TABLE IF NOT EXISTS push_log (
  bvid TEXT PRIMARY KEY,
  channel TEXT NOT NULL,
  pushed_ts INTEGER NOT NULL
);
"""

def connect(db_path: str) -> sqlite3.Connection:
    Path(os.path.dirname(db_path) or ".").mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(DDL)
    creator_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(creators)").fetchall()
    }
    if "priority" not in creator_columns:
        conn.execute(
            "ALTER TABLE creators ADD COLUMN priority INTEGER NOT NULL DEFAULT 0"
        )
    if "weight" not in creator_columns:
        conn.execute(
            "ALTER TABLE creators ADD COLUMN weight INTEGER NOT NULL DEFAULT 100"
        )
    conn.commit()
