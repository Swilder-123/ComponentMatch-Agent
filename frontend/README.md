# 独立 Streamlit 前端

源码位于 `src/componentmatch_frontend/`，`app.py` 为页面入口，`run.py` 为独立启动器。前端只依赖 Streamlit、Altair、HTTPX 和 Pydantic 接口契约；不导入 `componentmatch` 后端包，也不读取数据库、模型密钥或后端 `.env`。

从仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Target Frontend
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_frontend.ps1 -UiPort 8501 -ApiUrl http://127.0.0.1:8000
```

后端需在另一个终端运行。也可以直接启动：

```powershell
.\.venv-frontend\Scripts\python.exe frontend/run.py --port 8501 --api-url http://127.0.0.1:8000
```

访问 http://127.0.0.1:8501；Ctrl+C 退出。前端可以独立安装和启动，后端未启动时页面显示连接错误。当前 API 地址限制为本机 HTTP；跨机器部署不在本版范围内。

环境变量：`COMPONENTMATCH_API_URL`（默认 http://127.0.0.1:8000）、`COMPONENTMATCH_HTTP_TIMEOUT_SECONDS`（默认210秒，范围210–600）。启动器用白名单清理继承环境，不把后端凭据传给页面进程。不要用 `--env-file .env` 启动前端。

界面保留一个自然语言采购入口、五类案例、实际节点轨迹、Top 3、分项图表、证据、风险和错误状态。业务提交只走 Agent API，没有结构化主入口或运行时 Mock 开关。

澄清可以追加文字；也可以依据后端 `clarification_fields` 选择字段并显式提交 `confirmed_fields`。只发送用户选择且填写的条件；再次执行相同需求保留确认值，编辑原文后丢弃旧确认值。无法验证的硬条件仍不能通过确认绕过。

`api_client.py` 校验服务端响应契约，拒绝被篡改的评分；`presentation.py` 仅做中文标签、单位和图表排列。页面重绘、查看明细和选择案例不会重复提交请求。HTTP 不自动重试。

完整首次准备和常见问题见根目录 [README](../README.md)。
