# FastAPI 后端

后端源码在 `src/componentmatch/`，独立依赖在本目录 `pyproject.toml`。后端不安装前端包或 Streamlit，HTTP 契约由 `packages/contracts` 提供。整个仓库使用一个 uv 锁文件，安装时只选择所需包。

所有命令从仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Target Backend
# 编辑根目录 .env，填写后端密钥。
.\.venv-backend\Scripts\python.exe scripts/seed_demo.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start_backend.ps1 -ApiPort 8000
```

无需脚本权限的启动方式：

```powershell
.\.venv-backend\Scripts\python.exe scripts/start_backend.py --port 8000
```

启动器显式读取根目录 `.env`，应用模块本身仍只读进程环境。`DATABASE_URL` 的相对路径以仓库根目录为基准；seed、演示脚本和启动器读取同一份配置。已有数据库不自动刷新。`tzdata` 是 Windows 业务时区的显式依赖。

接口文档：http://127.0.0.1:8000/docs；`/health` 只检查进程。自然语言入口 `/api/v1/agent/matches` 会调用模型，结构化入口 `/api/v1/matches` 不调用模型。请求和响应契约见 `packages/contracts/src/componentmatch_contracts/`。

应用生命周期内复用编译图与模型连接池，每次请求的状态、计时和调用记录保持独立；关闭服务时释放 SDK 连接和数据库 engine。单次请求的数据库事务在模型解释前结束。日志记录请求 ID、节点、错误码、异常类型、候选数和降级原因，不记录异常正文、原文、Prompt 或凭据。

解析器按职责分为 `parser.py`（提取与归一化）、`numbers.py`（数值和金额）、`dates.py`（日期及时区）、`semantics.py`（否定和比较方向）。有限词法检查不能替代用户核对。

完整首次安装、排错与开发测试见根目录 [README](../README.md)。
