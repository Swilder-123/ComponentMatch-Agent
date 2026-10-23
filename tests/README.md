# 离线回归与启动检查

从仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Target Dev
.\.venv-dev\Scripts\python.exe -m pytest -q
.\.venv-dev\Scripts\ruff.exe check backend frontend packages scripts tests
.\.venv-dev\Scripts\ruff.exe format --check backend frontend packages scripts tests
.\.venv-dev\Scripts\python.exe scripts/check_docs.py
```

默认 pytest 使用临时 SQLite、FixedClock、显式 FakeTransport / MockTransport，并阻止外部 HTTP 传输；不修改项目数据库，不调用付费模型。

既有覆盖：契约、硬筛、评分、同分与去重、时间和证书、JSON 客户端、预算、图分支、解释证据、防篡改、API、HTTP 客户端、中文展示与 Streamlit AppTest。

本次新增：否定资质、交期上下限、模型裁剪原文后的完整性校验、空解释理由的零调用回退、显式字段确认与旧值清理、生命周期连接关闭、安全错误诊断、只读数据时效统计、前端与契约包的依赖方向。

安装两端环境后可执行零付费启动检查：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_demo.ps1 -SmokeTest -ApiPort 18011 -UiPort 18511
```

手动浏览器回归：`.venv-dev\Scripts\python.exe -m tests.phase5_local_check`。测试后端使用显式 Mock，前端使用独立 `.venv-frontend`，执行实际 HTTP 和桌面/窄屏检查；需要空闲的18010/18510端口、系统Chrome/Edge及首次下载Playwright的网络。使用当前 DEMO 库和业务时间，不刷新数据。日志在 `logs/refactor/`。这不是真实模型兼容性验证。

当前验证范围见 [验证索引](../docs/verification.md)。此前阶段记录保留在 [历史目录](../docs/history/README.md)。GitHub CI 在 Windows / Python 3.11 上运行离线 pytest、Ruff、文档本地链接检查和锁文件检查，不配置模型密钥，不自动执行上述手动浏览器或迁移检查。
