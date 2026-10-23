# 第四阶段 Streamlit Demo 验收记录

> 历史记录：保留当时的执行日期、测试数字和结论；本机路径已匿名化。当前安装、目录和行为请以 [README](../../README.md) 与 [验证索引](../verification.md) 为准。文中旧命令不作为当前启动指引。

执行日期：2026-10-21 至 2026-10-22（Asia/Shanghai）。

**结论：第四阶段已达到本轮验收条件，等待用户审核。**
已交付中文交互页面、统一 HTTP client、安全本地启动器和使用说明。
全量 **342 项测试通过**；Ruff 检查和格式检查通过；实际前后端启动、浏览器交互与窄屏检查通过。
本轮新增付费 DeepSeek 调用 **0 次**，未把 Mock 测试当作真实模型成功。

## 1. 已阅读与复用的契约

核对 README、架构/开发计划、第三阶段最终修复报告及真实联调记录，阅读实际
`schemas/agent.py`、`schemas/requirement.py`、`schemas/result.py`、API 路由和节点实现。
真实接口为 `POST /api/v1/agent/matches`，四种状态为 success、needs_clarification、no_match、error。
后端已有真实 node_trace，因此没有为了前端增加字段或修改图节点。

前端复用 AgentRequest/AgentResult 做 HTTP 边界校验。复用 Schema 中原有一致性校验不代表
重新实现评分：前端没有评分函数、数据库查询、模型客户端或新的排序算法。
推荐、金额、交期、权重、分项、贡献、排名、证据和风险全部读取 API。
只做金额分/元、百分比、显示小数位及图表数值类型转换；完整精度保留在指标明细。

## 2. 页面与交互

| 功能 | 实现与验证结论 |
|---|---|
| 中文工作台 | ComponentMatch Agent 标题、电子元器件智能供应商匹配系统副标题；DEMO 标识持续显示 |
| 布局 | 左侧案例/输入/操作与连接检查，右侧结果；原生容器/列/图表配少量 CSS；窄屏侧栏可折叠 |
| 五个案例 | 正常、成本优先、质量优先、信息缺失、约束过严；仅预填文本，不预填推荐、不自动提交 |
| 提交 | 统一 client 调现有自然语言接口；处理中禁用操作；队列只消费一次，普通重绘不重发 |
| 重试与清空 | 结果后可手动重新执行；清空移除输入与旧结果；输入改变时明确标记结果仍来自上次提交 |
| 解析 | 展示厂家、型号、数量、交期、单价预算、总预算、证书、偏好；草稿与已校验需求区分，未知字段不补全 |
| 澄清 | 展示后端问题并保留原文/草稿，用户输入补充内容并点击提交后附加原文；不自动填写 confirmed_fields |
| 流程 | 结束后直接展示实际 node_trace；没有轨迹时只显示静态架构，不伪造实时节点或耗时 |
| 推荐 | 动态 Top N（最多 3），供应商、报价、交期、总分、五维柱状对比及本次权重 |
| 明细 | 完整分数、原始指标、单位、加权贡献、证据字段/时间和风险原文可展开 |
| 无匹配 | 没有推荐卡片，展示真实报价计数、排除原因和逐条失败条件，不放宽约束 |
| 错误 | 后端安全错误码与中文建议；连接失败提示启动 FastAPI；前端等待超时不自动重试 |
| 降级与来源 | template 明确标记 Python 模板降级；source=mock 显著提示离线 Mock，不因 llm 模式误称真实调用 |

图表采用 Streamlit 原生 `st.bar_chart`，未引入其他前端框架或新业务依赖。

## 3. 启动与凭据隔离

Windows PowerShell 一键启动：

```powershell
.\scripts\start_demo.ps1
```

默认页面 <http://127.0.0.1:8501>，后端 <http://127.0.0.1:8000>。
脚本按 uv.lock 同步依赖，读取现有 SQLite 六表检查；数据库连接使用 mode=ro。
数据库缺失/不完整时明确失败，不自动创建、重置或刷新数据，不覆盖 `.env`。
只监听 loopback，不启动公网服务；端口占用不杀其他应用。

`start_demo.py` 为前端子进程构造白名单环境，仅保留运行必需变量及两项 UI 配置，
不传 DeepSeek、数据库、LangSmith 或其他凭据。前端不读取 `.env` 或 Streamlit secrets。
后端环境单独读取本地 `.env`。启动输出只显示密钥是否已配置，不显示密钥值。

前端配置：COMPONENTMATCH_API_URL 默认 http://127.0.0.1:8000；
COMPONENTMATCH_HTTP_TIMEOUT_SECONDS 默认 210 秒、允许 210–600 秒，连接超时 3 秒。
覆盖后端最大可配置 180 秒预算及余量；HTTP 层不重试，不承诺后端严格墙钟总时限。

分别启动与执行策略受限时的 Python 方式见 README；日常演示步骤见 demo_guide.md。

## 4. 实际执行与测试数量

本轮开始的真实基线为 **303 项**：第三阶段原有 290 项，加联调准备阶段 13 项保护测试。
本轮新增 **39 项**，没有删除或减少原有测试。

| 实际执行命令/检查 | 退出码 | 结果 |
|---|---:|---|
| `uv --cache-dir .uv-cache run --locked pytest -q --junitxml=logs/phase4/pytest.xml` | 0 | **342 passed in 11.40s** |
| `uv --cache-dir .uv-cache run --locked ruff check src scripts tests frontend` | 0 | All checks passed |
| `uv --cache-dir .uv-cache run --locked ruff format --check src scripts tests frontend` | 0 | 66 files already formatted |
| `.venv\Scripts\python.exe scripts/start_demo.py --check-only` | 0 | 依赖及 SQLite 六表检查通过；密钥仅检测存在，不联网 |
| `.\scripts\start_demo.ps1 -SmokeTest -ApiPort 18000 -UiPort 18501` | 0 | 实际启动 FastAPI 和 Streamlit；两个健康端点通过；自动停止后两个端口释放 |
| `.venv\Scripts\python.exe scripts/start_demo.py --frontend-only --smoke-test --ui-port 18503` | 0 | 单独启动前端通过，正常停止并释放端口 |
| `uv --cache-dir .uv-cache tool run --from playwright python logs/phase4/browser_check.py` | 0 | 本机 Chrome 无头浏览器 9 项检查通过；全部为隔离 Mock LLM 场景 |

新增测试分布：

- `tests/unit/test_frontend_client.py`：30 项。四状态 Mock HTTP、请求路径/内容/超时、
  连接与超时脱敏、无自动重试、无效响应、分数篡改拒绝、空/超长输入、配置白名单、
  金额/可选字段、前端环境凭据隔离、数据库只读检查，以及五个预置案例契约验证。
- `tests/integration/test_streamlit_app.py`：9 项。Streamlit AppTest 实际执行页面，
  覆盖初始/预填/清空、四状态、澄清重提交、模板降级与旧结果标识、连接故障、忙碌按钮禁用。
- 保留原有后端、评分、结构化 API、Agent、联调保护测试全部通过。

所有 pytest 默认受外部网络阻断，不能产生 DeepSeek 费用。
AppTest 的 HTTP 响应通过 MockTransport 注入；不是把整个 UI 或 HTTP client 替换成伪造成功。
案例响应由真实编译图、隔离 SQLite 和原 MatchingService 生成，模型部分明确使用 FakeTransport。

## 5. 浏览器与视觉检查

通过真实本地 HTTP 连接：Streamlit 18502 → FastAPI 18001 → 原工作流/服务 → 独立测试库，
LLM 明确为 Mock。`tests/phase4_browser_server.py` 仅在显式测试环境开关下运行，
测试子进程没有继承模型凭据；日常启动脚本不引用这个测试后端。

浏览器最终检查 9 项均通过：初始页面；质量案例与评分/证据/轨迹；综合案例；成本案例；
澄清补充后重新匹配；无匹配不出现推荐；超时不伪装成功；模板降级标记；390px 窄屏无横向溢出。
同时检查了 1440px 桌面布局、实际截图、评分图和窄屏侧栏。

截图保存在 `logs/phase4/`：ui_initial.png、ui_success_mock.png、ui_scores_mock.png、
ui_evidence_mock.png、ui_clarification_mock.png、ui_no_match_mock.png、ui_error_mock.png、
ui_template_mock.png、ui_mobile_mock.png。
**包含供应商的截图均为明确标记的 Mock LLM 测试结果，不是第四阶段真实模型演示记录。**

浏览器连接工具未响应后，改用临时 uv 工具环境中的 Playwright 与本机 Chrome。
备用 Chromium 下载已停止，未改变项目 pyproject.toml 或 uv.lock；浏览器测试工具不属于产品前端依赖。

## 6. 本轮发现并修复的问题

1. AppTest 相对文件路径按测试文件位置解析，初次测试找不到页面；改用绝对入口路径。
2. 当前 Streamlit 图表元素名称为 vega_lite_chart；更新测试检查，未删除图表断言。
3. 预置综合偏好改为后端已支持的“综合优先”表达，五个案例均通过原图/服务校验。
4. 浏览器自动化需等待预填文本回传和图表实际渲染；补充正确等待，避免把旧页面状态当作结果。
5. Windows venv Python 可能启动额外解释器子进程，原始 terminate 只停重定向进程。
   启动器改为停止自己拥有的子进程树；复测健康检查后端口全部释放，不影响其他应用。
6. 自定义侧栏最小宽度导致窄屏折叠后残留遮挡；移除强制宽度，复查截图和无横向溢出检查通过。

最终全量测试在上述修复后执行，结果见第 4 节。

## 7. 文件变更

| 文件 | 用途 |
|---|---|
| `frontend/__init__.py`、`frontend/app.py` | 中文工作台、交互状态、四种结果、明细和轨迹 |
| `frontend/api_client.py` | 统一 HTTP 请求、共享契约校验、安全错误、超时与本地地址配置 |
| `frontend/presentation.py` | 五个需求案例、中文标签、单位显示与图表数据整理 |
| `.streamlit/config.toml` | 本地主题、禁用用量遥测、headless 配置 |
| `scripts/start_demo.py`、`scripts/start_demo.ps1` | 凭据隔离、依赖/数据库检查、前后端启动和进程清理 |
| `tests/unit/test_frontend_client.py` | client/展示/安全/案例测试 |
| `tests/integration/test_streamlit_app.py` | 页面交互测试 |
| `tests/phase4_fakes.py`、`tests/phase4_browser_server.py` | 仅测试使用的离线图/HTTP 夹具 |
| `README.md`、`frontend/README.md`、`scripts/README.md`、`tests/README.md` | 启动、模块边界和测试说明 |
| `docs/architecture.md`、`docs/development_plan.md` | 同步当前阶段与前端状态，不改变架构业务判断 |
| `docs/demo_guide.md`、`docs/history/phase4_verification.md` | 演示指南与本报告 |
| `logs/phase4/`（Git 忽略） | pytest XML/输出、规范输出、浏览器截图与检查、安全及完整性证明 |

38 个原后端源码、数据库、依赖文件 SHA-256 前后相同。没有修改 src/、评分规则、数据库设计、
数据库内容、LangGraph 主流程或依赖锁。没有提交 Git 或部署公网。
扫描本轮源码、文档和文本/JSON 日志未发现当前配置密钥；模板密钥仍为空。
前端静态导入检查没有数据库、模型客户端、服务、评分或后端 Settings 导入。
测试端口 18000、18501、18001、18502、18503 均已释放，测试服务已清理。

## 8. 仍存在的限制

- **第四阶段未新增真实付费调用。** 前端与当前真实模型的一体化在线演示未重新执行；
  真实后端能力依据第三阶段三个场景记录，前端链路依据本轮离线/本地 HTTP 验证。
- DEMO 数据会随实际业务日期变旧/失效；启动器只检查完整性，不自动刷新时效。
  未来无匹配必须按真实排除原因解释，不修改时钟或规则使案例强行成功。
- 澄清采用显式文本补充/原文修订，不做自动确认或多轮持久化记忆。
  有限自然语言解析仍需用户核对字段，不能保证任意表达无遗漏。
- 请求保护限于单个 Streamlit 会话，不等于跨会话幂等或取消后端任务。
  刷新/关闭页面可能丢失会话状态；前端超时后后端可能仍在处理。
- 无生产登录、并发限流、长期审计、公开部署或压力测试，仅限本机演示。
- CSS 使用少量 Streamlit test-id 选择器；未来升级 Streamlit 后应复查窄屏样式。

在用户要求的“不追加付费调用”边界内，第四阶段功能、离线集成、实际启动与视觉验收完成。
本轮停止，不自行进行下一阶段或新的真实模型调用。
