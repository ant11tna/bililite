此目录用于存放离线安装的 wheel 包。

在可联网环境中执行以下命令生成并填充此目录：

```bash
python -m pip download -d vendor/wheels -r requirements.lock
```

或显式列出依赖：

```bash
pip download \
  fastapi uvicorn pydantic PyYAML typing-extensions \
  -d vendor/wheels
```
