# Bililite (bili-aggregator)

## 配置文件与本地私密覆盖

项目支持两层配置：

- `config.yaml`：基础配置，**可以提交到仓库**。
- `config.local.yaml`：本地私密覆盖配置，**仅本机使用，不提交**（已通过 `.gitignore` 忽略）。

读取配置时会按下面顺序加载并深度合并：

1. 先读取 `config.yaml`
2. 再读取 `config.local.yaml`
3. 执行深度合并（dict 递归合并；list 直接覆盖；标量直接覆盖）

统一入口：`app/config.py` 中的 `load_config()`。

### 推荐做法

在 `config.yaml` 中保留可公开字段，敏感字段留空。例如：

```yaml
push:
  enabled: true
  provider: "serverchan"
  serverchan:
    sendkey: ""
```

然后只在本地新建 `config.local.yaml`（不要提交）：

```yaml
push:
  serverchan:
    sendkey: "你的真实 SENDKEY"
bilibili:
  cookie: "你的真实 Cookie"
```

这样在运行 `python -m app.push_daily` 时，会自动读取本地覆盖后的 `sendkey` 并执行推送。

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

## 一键启动（0.0.0.0:9000）

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 9000
```

## Server酱每日推送（今日必看候选）

### 配置

在 `config.yaml` 中补充：

```yaml
push:
  enabled: true
  provider: "serverchan"
  serverchan:
    sendkey: ""
  daily:
    group: "必看"
    hours: 24
    limit: 50
    sample: 5
    max_items: 5
```

并在本地 `config.local.yaml` 填写真实 `sendkey`：

```yaml
push:
  serverchan:
    sendkey: "你的 SENDKEY"
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
curl -i http://127.0.0.1:9000/docs
curl -i "http://127.0.0.1:9000/api/videos?limit=1"
curl -i http://127.0.0.1:9000/api/creator-groups
curl -i http://127.0.0.1:9000/api/creators
```


## Creator 维度增强（priority/weight）

数据库 `creators` 表新增字段（兼容旧库自动迁移）：

- `author_name`
- `priority INTEGER NOT NULL DEFAULT 0`
- `weight INTEGER NOT NULL DEFAULT 1`

启动任意 API/抓取流程后会自动执行迁移。

新增 API：

- `GET /api/creators`：查看所有 creator 的 `uid/author_name/enabled/priority/weight`
- `POST /api/creators`：批量更新 creator 的 `enabled/priority/weight`

示例：

```bash
curl -X POST http://127.0.0.1:9000/api/creators \
  -H 'Content-Type: application/json' \
  -d '[{"uid":123456,"priority":10,"weight":3,"enabled":true}]'
```
