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

## 自测命令

```bash
curl -i http://127.0.0.1:8000/docs
curl -i "http://127.0.0.1:8000/api/videos?limit=1"
curl -i http://127.0.0.1:8000/api/creator-groups
```
