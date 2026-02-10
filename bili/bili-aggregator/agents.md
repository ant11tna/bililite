# agents.md（Codex 执行指南）

> 面向：在本仓库中运行/修改代码的自动化 Agent（如 Codex）。
> 原则：**可执行命令优先**；避免臆测；对外部依赖、鉴权与反爬保持谨慎；禁止提交任何真实 Cookie/Token。

## 1) 项目概览

- **项目名**：Bililite / bili-aggregator
- **功能**：抓取 B 站 UP 主视频（多种抓取源可选），写入本地 SQLite；提供 FastAPI Web 服务与前端静态页用于浏览/筛选；支持 Server酱每日推送“今日必看候选”。
- **主要模块**
  - 抓取：`app/fetcher.py` + `app/sources/*`
  - Web API / 静态页：`app/main.py` + `web/*`
  - 推送：`app/push.py`、`app/push_daily.py`
  - 数据库：`app/db.py`（SQLite，默认 `./data/app.db`）
- **关键配置**：`config.yaml`

## 2) 仓库结构（与 agent 相关）

仓库根目录：`bili/bili-aggregator/`

- `app/`
  - `main.py`：FastAPI 入口（挂载 `web/` 作为静态资源；提供 `/api/*`）
  - `fetcher.py`：抓取主流程 `run_fetch(config)`
  - `db.py`：SQLite schema 初始化与连接
  - `schemas.py`：Pydantic 模型
  - `push.py` / `push_daily.py`：Server酱推送与每日任务入口
  - `sources/`
    - `stub.py`：本地模拟源（开发/演示）
    - `rsshub.py`：RSSHub 源（从 RSS 解析）
    - `bili_api.py`：B 站 API 源（requests）
    - `bili_dynamic.py`：动态页/关注流源（需要 cookie）
- `web/`：纯静态前端（`index.html`/`app.js`/`styles.css`）
- `data/`：运行时数据目录（默认 SQLite：`data/app.db`）
- `vendor/wheels/`：离线安装 wheelhouse（README 说明）
- `requirements.txt`：运行依赖（含 `feedparser`、`requests`）
- `requirements.lock`：离线安装锁定（当前只列出部分核心依赖）
- `run_fetch.bat`：Windows 一键抓取（使用 `.venv`）
- `run_server.bat`：Windows 一键启动服务（127.0.0.1:9000）

## 3) 安装、运行、测试（可直接执行）

### 3.1 Python 环境
建议使用 Python 3.10+（本仓库未提供版本约束文件；以本机可运行 FastAPI/uvicorn 为准）。

### 3.2 安装依赖（联网环境）
在项目根目录（`bili/bili-aggregator/`）执行：
```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# macOS/Linux:
# .venv/bin/python -m pip install -U pip
# .venv/bin/python -m pip install -r requirements.txt
```

### 3.3 离线安装（无需联网）
按 README 约定（wheel 已准备在 `vendor/wheels/`）：
```bash
pip install --no-index --find-links vendor/wheels -r requirements.lock
```

> 注意：`requirements.lock` 当前不包含 `feedparser`、`requests`，若你离线环境需要 RSSHub / B 站抓取源，需确保 wheelhouse 与 lock 覆盖完整依赖集合。

### 3.4 启动 Web 服务
**方式 A：bat 脚本（Windows）**
```bat
run_server.bat
```
脚本等价于：
```bash
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 9000
```

**方式 B：命令行**
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3.5 执行抓取（写入 SQLite）
**方式 A：bat 脚本（Windows）**
```bat
run_fetch.bat
```

**方式 B：命令行调用 run_fetch**
```bash
python -c "import yaml; from app.fetcher import run_fetch; cfg=yaml.safe_load(open('config.yaml','r',encoding='utf-8')); print(run_fetch(cfg))"
```

### 3.6 推送（Server酱每日“必看”）
```bash
python -m app.push_daily
```

### 3.7 自测（当前仓库未包含 pytest 测试）
用 smoke test 验证 API 可用（README 提供示例）：
```bash
curl -i http://127.0.0.1:9000/docs
curl -i "http://127.0.0.1:9000/api/videos?limit=1"
curl -i http://127.0.0.1:9000/api/creator-groups
```
> 端口取决于你启动 uvicorn 时的 `--port`。

## 4) Helpful CLI 工具（建议 agent 常用）

- `curl`：API 冒烟与调试（见 3.7）
- `sqlite3`：直接检查数据库内容（建议只读）
  ```bash
  sqlite3 ./data/app.db ".tables"
  sqlite3 ./data/app.db "select count(*) from videos;"
  ```
- `python -m uvicorn`：本地启动服务
- Windows 快捷：
  - `run_server.bat`
  - `run_fetch.bat`

## 5) MCP servers（本仓库现状）

未在仓库内发现 MCP 配置文件（如 `mcp.json` / `mcp.yaml` 等）。  
因此默认假设：**agent 仅使用本地 CLI + 代码修改**，不依赖外部 MCP 工具链。

## 6) 实现一个功能的推荐工作流（面向本仓库）

### A) 先定位改动边界
1. 该需求属于：
   - 抓取链路（`app/fetcher.py` / `app/sources/*`）？
   - 存储与查询（`app/db.py` / `app/main.py` SQL）？
   - 前端交互（`web/*`）？
   - 推送逻辑（`app/push.py`）？
2. 是否涉及 `config.yaml` 新字段？若是，必须同时更新：
   - `config.yaml`（示例/默认值）
   - README（若对用户可见）
   - 代码中的 `load_config()` 使用方式

### B) 按模块实施（建议顺序）
1. **数据模型/DB**  
   - 如果新增字段：先在 `app/db.py` 增加 schema（注意 SQLite 迁移策略；当前项目偏“初始化建表”风格）
2. **抓取/解析**  
   - 优先在对应 source 文件内新增字段解析，统一输出 `v: Dict`（参照 `upsert_video()` 读取字段）
3. **写库**  
   - `app/fetcher.py` 的 `upsert_video()`：确保新增字段进入 INSERT/UPDATE
4. **API 输出**  
   - `app/schemas.py`：补充响应模型
   - `app/main.py`：补充查询与返回字段
5. **前端**  
   - `web/app.js`：渲染/筛选/UI 调整
6. **验证**  
   - 跑一次 `run_fetch` 写入数据
   - 启动服务并用 curl 检查接口
   - 关键页面（`/`）打开检查

### C) 验证清单（提交前）
- [ ] `config.yaml` 不包含真实 Cookie/Token（尤其是 `bilibili.cookie`、`serverchan.sendkey`）
- [ ] `run_fetch` 与 `run_server` 在干净环境可运行
- [ ] API 冒烟通过（3.7）
- [ ] DB 写入逻辑不破坏旧数据（`ON CONFLICT` 更新字段要谨慎）

## 7) 抓取源与配置要点（避免 agent 误用）

`config.yaml`：
- `fetch.source` 支持：
  - `stub`：`app/sources/stub.py`
  - `rsshub`：`app/sources/rsshub.py`（依赖 `rsshub.base_url` + `route_template`）
  - `bili_api`：`app/sources/bili_api.py`（使用 `requests`）
  - `bili_dynamic`：`app/sources/bili_dynamic.py`（**必须提供** `bilibili.cookie`，否则会 `RuntimeError`）

安全与合规：
- 不要把真实 `SESSDATA` / `bili_jct` / `DedeUserID` 写入仓库与补丁。
- 如果需要让 agent 在本地调试 cookie：使用本机 `.env` 或私有配置文件，并在 `agents.md`/README 中声明“不提交”。

## 8) 指向更多项目内说明（task-specific guidance）

- 基础使用、离线安装、推送配置：`README.md`
- 运行时配置示例：`config.yaml`
- 抓取逻辑入口：`app/fetcher.py`
- API 路由与 SQL：`app/main.py`
- 推送实现：`app/push.py`
- 各抓取源实现：`app/sources/*.py`
