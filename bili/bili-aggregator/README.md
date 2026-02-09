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

## 自测命令

```bash
curl -i http://127.0.0.1:8000/docs
curl -i "http://127.0.0.1:8000/api/videos?limit=1"
curl -i http://127.0.0.1:8000/api/creator-groups
```
