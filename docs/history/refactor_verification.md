# 前后端分离与新电脑启动验证

> 历史记录：保留当时的执行日期、测试数字和结论；本机路径已匿名化。当前安装、目录和行为请以 [README](../../README.md) 与 [验证索引](../verification.md) 为准。文中旧命令不作为当前启动指引。

日期：2026-10-23（北京时间）。本次以工作区源码为准；仓库尚无已有提交历史。前端继续使用 Streamlit，后端继续使用 FastAPI / LangGraph，业务评分规则不变。

## 已完成

- 后端移动到 `backend/src/componentmatch/`，前端移动到 `frontend/src/componentmatch_frontend/`。
- 三个独立包：后端、前端、只依赖 Pydantic 的 `componentmatch-contracts`。公共 HTTP 契约移出后端，内部数据库快照留在后端。
- 用根 uv workspace / 锁文件管理版本，分别安装到 `.venv-backend`、`.venv-frontend`，联合开发使用 `.venv-dev`。不使用从旧电脑拷来的 `.venv`。
- 明确声明直接依赖，包括后端 Windows 业务时区所需的 `tzdata`、启动脚本所用的 `python-dotenv`、前端图表所用的 `altair`。
- 修复交期下限和严格比较被当作含等号上限的问题；对不支持的方向返回澄清，不擅自转换。
- 识别常见资质否定/可选表达；不同子句中的必需资质仍单独校验，不能通过“可选”取消后续硬条件。
- 任一推荐没有可选合法理由时直接输出事实模板，不发送注定失败的解释请求。
- 澄清响应新增 `clarification_fields`，页面支持显式提交所选 `confirmed_fields`；没有选择或填写不会提交。修改原文或追加补充文字后清除旧确认值。
- 编译图与模型客户端按应用生命周期复用；并发请求状态独立，退出关闭拥有的 SDK 连接和数据库 engine。
- 日志增加错误码、异常类型、候选数和模板原因，不记录异常正文、采购原文、Prompt 或密钥。
- 启动器只读提示报价和证书时效；准备失败定位到具体步骤，不自动重置旧库。
- 重写根 README 及前端、后端、数据、脚本说明，同步当前架构与开发路径。

## 自动化回归

| 检查 | 结果 |
| --- | --- |
| `.venv-dev\Scripts\python.exe -m pytest -q --junitxml=logs/refactor/pytest.xml` | **403 passed in 11.71s** |
| `.venv-dev\Scripts\ruff.exe check backend frontend packages scripts tests` | 通过 |
| `.venv-dev\Scripts\ruff.exe format --check backend frontend packages scripts tests` | 通过 |
| `uv --cache-dir .uv-cache lock --check` | 通过 |

此前359项回归保留；新增44项覆盖语义边界、空理由回退、字段确认、生命周期、并发隔离、安全日志、数据只读时效、包依赖边界与 seed 配置一致性。健康检查的阶段标签从早期 `deterministic_matching` 同步为 `agent_matching`。

默认测试使用临时库、固定业务时钟和显式模型替身，阻止默认外部 HTTP 传输。测试不使用现有 DEMO 库，也不调用付费模型。

## 隔离安装与实际启动

独立环境运行 `python -I` 导入检查：

- 前端可以导入完整页面；找不到后端包、SQLAlchemy 和 LangGraph。
- 后端可以导入 API；找不到前端包和 Streamlit。
- 首次隔离检查暴露缺少 tzdata，已补为后端直接依赖后复验通过。这是完整开发环境测试无法单独发现的问题。

实际执行 `start_demo.ps1 -SmokeTest -ApiPort 18011 -UiPort 18511`，FastAPI / Streamlit 均能启动和响应，随后清理本次子进程。数据时效检查对现有库报告：18条活跃报价中16条满足报价时效，1条过期、1条超过7日，1张核验资质已过期；这是时效统计，实际匹配仍执行全部硬约束。

分别通过 `scripts/start_backend.py` 和 `frontend/run.py` 在18014/18514启动，两端健康检查通过；向真实结构化 API 提交一次请求，HTTP 200，返回3家供应商，模型调用0次。测试后端口释放。证据在 `logs/refactor/standalone.json` 和对应两份日志。

## 只复制源码的新目录验证

运行 `.venv-dev\Scripts\python.exe -m tests.clean_install_check`：

1. 将源码、包配置、锁文件和空模板复制到全新临时目录，没有复制用户 `.env`、数据库、虚拟环境或开发测试环境。
2. 执行与 README 相同的 `scripts/setup.ps1`，生成两个独立环境和空密钥 `.env`。
3. 执行 `seed_demo.py` 创建新库，再执行一次确认 `unchanged`。
4. 验证两端包隔离，执行三档确定性偏好和严格预算场景。
5. 执行一键启动 SmokeTest，两个服务健康检查通过并退出。
6. 检查后清理本次生成的临时目录。

全部通过，模型调用0次。证据在 `logs/refactor/clean_install.json` 和 `clean_install.log`。该检查复用了本机 uv 管理的 Python 安装，实际验证的是源码迁移、依赖安装、灌数和启动；没有模拟安装操作系统或 uv 本身。

## 实际浏览器检查

执行 `.venv-dev\Scripts\python.exe -m tests.phase5_local_check`，本地浏览器 → 独立前端环境 → FastAPI 测试后端 → 原图和服务 → 现有 DEMO 库。

- 13项桌面/窄屏检查通过：唯一自然语言主入口、三档偏好、证据和轨迹、信息缺失、补充提交、无匹配、超时、模板降级、实际来源标记、窄屏无横向溢出、中文展示。
- 浏览器产生11次业务请求，全部为 Agent API；另外6次直接结构化 API 检查均为零模型调用。
- 模型全部为显式 Mock；后端记录付费尝试0次，没有将其当作真实 DeepSeek 成功证据。
- 检查了1440px桌面和390px手机宽度截图。显式字段确认另有 AppTest 操作回归，包括旧值清理和不完整确认不发请求。
- 测试后18010/18510端口释放。截图和请求审计位于 `logs/refactor/`。

## 当前边界

未更改用户原有 `.env` 或数据库，未追加真实 DeepSeek 调用，未部署公网。自然语言的词法守卫仍是有限覆盖，不能证明任意表达完整提取；必须核对结构化条件。请求预算仍为协作式，同步工作线程不能强制中断。根 README 的当前目录和命令优先于此前历史阶段报告。
