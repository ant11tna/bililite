# Bililite (bili-aggregator)

## 离线安装（无需联网）

> 依赖 wheel 由你在本机生成并放入 `vendor/wheels/`。

```bash
pip install --no-index --find-links vendor/wheels -r requirements.lock
```

## 本机生成 wheelhouse（联网环境）

在本机（可联网）执行：

```bash
python -m pip download -d vendor/wheels -r requirements.lock
```

或按需显式列出依赖（与 requirements.lock 保持一致）：

```bash
pip download \
  fastapi uvicorn pydantic PyYAML typing-extensions \
  -d vendor/wheels
```

## 一键启动（0.0.0.0:8000）

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Server酱每日推送（今日必看候选）

### 配置

在 `config.yaml` 中补充：

```yaml
push:
  enabled: true
  provider: "serverchan"
  serverchan:
    sendkey: "你的 SENDKEY"
  daily:
    group: "必看"
    hours: 24
    limit: 50
    sample: 5
    max_items: 5
```

> 若 `group` 为空或不存在，会自动退化为所有 `enabled` creators。
> `max_items` 用于限制最终推送条数，已推送过的内容会自动去重过滤。

### 手动运行

```bash
python -m app.push_daily
```

### 定时任务

**Windows 任务计划程序**

1. 打开“任务计划程序” → “创建基本任务”。
2. 触发器选择“每天”。
3. 操作为“启动程序”，程序填写 `python`，参数填写 `-m app.push_daily`，起始于项目根目录。

**crontab（Linux/macOS）**

```bash
crontab -e
```

添加一条每天 9:00 执行的任务：

```bash
0 9 * * * cd /path/to/bili-aggregator && python -m app.push_daily
```

## WSL 可复制验收命令（UP 主白名单 + 权重抽样 + 去重）

```bash
# 1) 用 stub 跑一轮抓取（覆盖配置里的慢 sleep，快速写数）
python -c "import yaml; from app.fetcher import run_fetch; cfg=yaml.safe_load(open('config.yaml','r',encoding='utf-8')); cfg['fetch']['source']='stub'; cfg['fetch']['polite_sleep_ms']=[0,0]; print(run_fetch(cfg))"

# 2) 用 sqlite3 设置部分 creators 的 priority / weight（也可直接改 config.yaml 再 run_fetch）
sqlite3 data/app.db "UPDATE creators SET priority=1, weight=300 WHERE uid=123456; UPDATE creators SET priority=0, weight=50 WHERE uid=234567;"

# 3) 清空去重表，启动服务并验证 /api/daily 返回 >0
sqlite3 data/app.db "DELETE FROM push_log;"
python -m uvicorn app.main:app --host 0.0.0.0 --port 9000
curl -s "http://127.0.0.1:9000/api/daily?group=%E5%BF%85%E7%9C%8B&hours=72&limit=20&sample=5" | head

# 4) 写入两条 push_log，再次调用 /api/daily，验证数量减少或为 0（dedupe 生效）
sqlite3 data/app.db "INSERT OR IGNORE INTO push_log(bvid,channel,pushed_ts) SELECT bvid,'serverchan',strftime('%s','now') FROM videos ORDER BY pub_ts DESC LIMIT 2;"
curl -s "http://127.0.0.1:9000/api/daily?group=%E5%BF%85%E7%9C%8B&hours=72&limit=20&sample=5" | head
```

## 自测命令

```bash
curl -i http://127.0.0.1:8000/docs
curl -i "http://127.0.0.1:8000/api/videos?limit=1"
curl -i http://127.0.0.1:8000/api/creator-groups
```
