# 安装与运行脚本

从仓库根目录执行。完整新电脑步骤以 [根 README](../README.md) 为准。Windows 脚本可以通过 `powershell -NoProfile -ExecutionPolicy Bypass -File ...` 执行，无需更改系统策略。

| 脚本 | 用途 |
| --- | --- |
| `setup.ps1` | 按锁文件创建后端/前端独立环境，缺失时复制空密钥模板；不改数据、不调用模型。 |
| `setup.ps1 -Target Backend/Frontend/Dev` | 选择单端或开发测试环境。 |
| `start_demo.ps1` | 安装检查、数据库只读及时效检查，再用各自解释器启动两个服务。 |
| `start_demo.ps1 -CheckOnly` | 只做准备检查；不启动、不验证模型。 |
| `start_demo.ps1 -SmokeTest` | 启动并健康检查后自动关闭；不提交业务请求。 |
| `start_backend.ps1` / `start_backend.py` | 仅启动后端，显式加载根 `.env`。 |
| `start_frontend.ps1` / `frontend/run.py` | 仅启动前端，清理凭据环境，不读取 `.env`。 |
| `seed_demo.py` | 显式初始化 DEMO 库；已有同版本数据不刷新。 |
| `demo_match.py` | 使用当前业务时间验证三种确定性偏好和严格预算，不调用模型。 |
| `check_docs.py` | 离线检查 Git 跟踪/待提交 Markdown 的本地链接及个人主目录路径。 |
| `check_deepseek.py` | 真实模型联调工具；默认只预检查，添加 `--allow-paid-api` 才调用模型。 |

各脚本均使用根目录路径，不需要激活虚拟环境。`seed_demo.py` 和 `demo_match.py` 读取根 `.env` 的 DATABASE_URL，也支持 `--database-url` 显式覆盖。详细换库方式见 [data/README.md](../data/README.md)。

独立后端环境没有 Streamlit；独立前端环境没有后端包、SQLAlchemy、LangGraph 或模型 SDK。联合启动器由后端解释器运行，再用 `.venv-frontend` 的解释器启动页面。开发与默认 pytest 使用 `.venv-dev`，不使用复制来的旧 `.venv`。

日志在 `logs/demo-时间-进程号/`。退出只清理本次拥有的进程；端口被占用时要求换端口，不结束其他程序。
