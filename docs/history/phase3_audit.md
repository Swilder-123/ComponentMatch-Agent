# 第三阶段代码审查与验收报告

> 历史记录：保留当时的执行日期、测试数字和结论；本机路径已匿名化。当前安装、目录和行为请以 [README](../../README.md) 与 [验证索引](../verification.md) 为准。文中旧命令不作为当前启动指引。

审查日期：2026-10-21（Asia/Shanghai）。项目：ComponentMatch Agent。

本轮范围：检查现有代码、设计、依赖、迁移环境、数据库与测试；仅恢复本机运行环境并生成审查材料。没有开发缺失业务功能、重构、修改评分或数据库设计、创建前端、提交 Git、覆盖 `.env` 或删除原有文件。所有供应商数据均为 DEMO。

## 1. 验收结论

| 阶段（按本次用户定义） | 状态 | 依据 |
| --- | --- | --- |
| 第一阶段：架构设计 | **完成** | 需求、架构、数据库、评分、开发计划五份设计文档齐全；目录、依赖、配置与健康检查存在。文档中的交付状态已经落后于代码，需要同步。 |
| 第二阶段：数据库与确定性评分 | **完成** | 六张表、种子、MatchingService.match()、硬筛、评分、Top 3、证据和结构化 API 均可运行；对应原阶段的 109 项测试全部通过。 |
| 第三阶段：DeepSeek + LangGraph | **部分完成，尚未通过完整验收** | 客户端、解析、编译图、条件分支、受限解释、自然语言 API 均已实现并接入，新增 71 项测试通过；但存在可复现的解析防护缺口、总时限缺口、静态检查失败、文档未同步，以及真实 DeepSeek 验证缺失。 |

**不建议直接进入第四阶段 Streamlit 正式开发。** 应先补齐第 9 节的第三阶段验收任务。第三阶段不是“完全没做”，也不能仅凭 180 项测试通过认定“已经完成”。

阶段编号说明：`docs/development_plan.md` 的旧路线把数据、评分分为两个阶段，将“模型与图”编号为 4、“前端”编号为 5；本报告统一采用用户本轮的四阶段划分，避免编号误导。

## 2. 当前目录结构

```text
ComponentMatch Agent/
├── .env.example                  # 有；.env 不存在
├── .python-version               # 3.11
├── .gitignore
├── pyproject.toml
├── uv.lock
├── README.md                     # 仍描述第二阶段，已过时
├── docs/
│   ├── requirements.md
│   ├── architecture.md
│   ├── database_design.md
│   ├── scoring_design.md
│   ├── development_plan.md
│   ├── phase2_verification.md
│   ├── agent_workflow.mmd
│   ├── examples/
│   │   ├── agent_request.json
│   │   └── agent_response.mock.json
│   └── phase3_audit.md            # 本报告
├── src/componentmatch/
│   ├── core/                     # config.py、clock.py、identity.py
│   ├── models/                   # base.py、catalog.py：六表 ORM
│   ├── db/                       # session.py、repositories.py、seed.py
│   ├── schemas/                  # requirement.py、snapshot.py、result.py、agent.py
│   ├── scoring/                  # constraints.py、engine.py、weights.py
│   ├── services/matching.py
│   ├── llm/                      # client.py、parser.py、explainer.py，均有实现
│   ├── agent/                    # state.py、nodes.py、graph.py，均有实现
│   └── api/                      # main.py、routes.py、agent_routes.py
├── scripts/
│   ├── seed_demo.py
│   ├── demo_match.py
│   └── check_deepseek.py          # 可选真实调用脚本；本轮未执行
├── tests/
│   ├── conftest.py
│   ├── agent_fakes.py
│   ├── export_agent_example.py
│   ├── unit/                     # 5 个 test_*.py 文件
│   └── integration/              # 4 个 test_*.py 文件
├── data/componentmatch.db        # 复制过来的数据库，完整且保留
├── frontend/README.md            # 只有占位说明，无 app.py
├── .venv/                       # 本轮按锁文件重建的本机环境
├── .venv.migration-backup-20261021/ # 原虚拟环境，完整保留
└── logs/phase3_audit/             # 本轮执行日志、离线复现脚本及隔离测试数据库
```

省略了 `__init__.py`、各子目录 README、`.gitkeep` 与缓存目录。关键生产代码、九个测试模块及设计文档均已核对。没有发现适用于本目录的 AGENTS.md。

## 3. 环境、依赖与跨电脑迁移

| 项目 | 实际结果与处理 |
| --- | --- |
| 系统 Python | `<CONDA_HOME>/python.exe`，3.13.9；未修改。项目使用自己的 3.11 环境。 |
| uv | 本机 0.11.18，可用。旧虚拟环境记录为 uv 0.11.23，版本不同未阻止锁定同步。 |
| 原虚拟环境 | `.venv/pyvenv.cfg` 的 home 指向旧电脑 `%USERPROFILE%\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none`；直接启动报 `uv trampoline failed to spawn Python child process / entity not found (os error 2)`。 |
| 修复 | 核验移动源、目标均位于工作区后，将旧 `.venv` 改名保留，再执行 `uv --cache-dir .uv-cache sync --locked`。新环境 Python 3.11.15，home 位于当前用户 `%USERPROFILE%\AppData\Roaming\uv\python\...`。未沿用旧路径。 |
| 锁与依赖 | sync 退出 0，解析 85 个包、安装 83 个包；`uv lock --check` 与 `uv pip check` 均退出 0。pyproject.toml 和 uv.lock 未修改。解析数与实际安装数不是同一统计口径。 |
| 关键版本 | FastAPI 0.156.4、LangGraph 1.2.16、langchain-deepseek 1.1.1、SQLAlchemy 2.1.5、Pydantic 2.14.1、OpenAI SDK 3.35.1、LangSmith 0.14.11、pytest 9.1.1、Ruff 0.17.1、Uvicorn 0.54.0。这是本机安装快照，不代表供应商线上兼容性结论。 |
| 配置 | `.env` 不存在。进程、用户级和系统级 `DEEPSEEK_API_KEY` 均未设置。未输出任何密钥内容，也未新建或覆盖 `.env`。 |
| 示例一致性 | `.env.example` 的 8 个变量与 Settings 字段一一对应：API Key、base URL、模型、模型超时、重试、token 上限、Agent 总时限、数据库 URL；默认值一致。应用只读进程环境，`.env` 需通过 uv `--env-file` 显式加载。 |
| 数据库 | 默认 `sqlite:///./data/componentmatch.db` 存在、可读；无需恢复或重建原库。相对路径依赖当前工作目录，应从项目根目录启动。 |
| 其他路径 | 在 src、scripts、tests、设计文档、README、依赖配置中搜索旧用户/绝对路径，未发现需要修复的业务硬编码路径。旧路径问题集中在复制的虚拟环境。 |
| Git 历史 | 存在 `.git`，但 `git rev-parse --verify HEAD` 退出 128，提示缺少有效 revision；项目文件显示未跟踪。无法通过提交历史确认旧电脑最后一次交付。没有执行提交。 |

**真实模型测试条件：当前不具备。** 没有可用配置密钥，也没有账户权限、余额、模型可用性的验证证据。默认模型字符串为 `deepseek-flash`，配置与代码一致；其在用户账户中的实际可用性未验证。即使后续配置密钥，也应在用户确认后才执行付费调用。本轮真实 DeepSeek 调用数为 **0**。

原库的只读检查：`PRAGMA integrity_check` 返回 `ok`，`PRAGMA foreign_key_check` 返回空；表名与 ORM 完全一致。快照为 `2026-10-21T08:20:53.174039Z`（上海 16:20:53），schema-v1 / DEMO-v2。本次业务运行没有用快照时间回拨时钟。

## 4. 第二阶段回归与确定性规则

| ORM 类 / 表 | 实际行数 | 核对结果 |
| --- | ---: | --- |
| Component / components | 6 | 厂家 + 完整料号唯一身份，参考价、币种、时间配对约束 |
| Supplier / suppliers | 12 | 虚构供应商，状态/类型约束、供应商名称唯一 |
| Offer / offers | 18 | FK、价格/库存/MOQ/包装倍数/交期/时效约束，允许同家多报价 |
| SupplierCertification / supplier_certifications | 11 | MOCK 编号、有效期、核验状态、FK 与唯一约束 |
| PerformanceRecord / performance_records | 66 | 供应商 + 型号 + 完整月份；分子/分母约束，窗口唯一 |
| DemoMetadata / demo_metadata | 1 | 单行 DEMO 元信息及版本、快照时间 |

定义位于 `src/componentmatch/models/catalog.py`，通用来源标识和 UTC 类型位于 `models/base.py`。`db/session.py` 在应用连接上启用外键，并显式控制读取事务。

种子 `db/seed.py` 和 `scripts/seed_demo.py` 完整。除原测试验证之外，本轮用原 CLI 在 `logs/phase3_audit/seed_cli.db` 创建新的隔离演示库，再重复执行：第一次 `created`，第二次 `unchanged`，计数和快照时间相同。没有改写原数据库。

`MatchingService.match(ProcurementRequirement)` 仍存在并可调用，原结构化 API 继续使用它。检索、过滤、评分被组织为同一服务的 `prepare()`、`filter_candidates()`、`score_and_rank()`，图节点复用这些方法；**图不逐字调用 match() 外壳，但使用同一业务实现，未发现另一套评分算法**。

硬筛保留精确料号/厂家、状态、数据完整性、库存、MOQ、包装倍数、交期、独立单价/总预算、证书、报价时效。合格报价才进入 Decimal 评分；默认质量 30%、价格 20%、交期 25%、准时交付 20%、响应 5%，另有 cost / delivery / quality 命名档位。

评分使用固定锚点、六位精度、缺历史记 0、小样本封顶 50；同家只选最佳报价，再取最多三家。排序顺序为总分降序、质量分降序、交期升序、总货款升序、供应商 ID、报价 ID。响应包含分项原值、权重、贡献、记录级证据与风险。

本次 `demo_match.py` 使用真实业务时钟（上海 22:45:20）得到：

| 场景 | 第 1 名 | 第 2 名 | 第 3 名 | 状态 |
| --- | --- | --- | --- | --- |
| balanced | DEMO 02 / 83.500000 | DEMO 03 / 80.226950 | DEMO 01 / 60.680851 | success |
| cost | DEMO 01 / 73.180851 | DEMO 03 / 70.893617 | DEMO 02 / 67.000000 | success |
| quality | DEMO 02 / 84.500000 | DEMO 03 / 78.893617 | DEMO 01 / 54.680851 | success |
| 单价上限 1 分 | 无 | 无 | 无 | no_match；13 条报价触发 UNIT_PRICE_OVER_LIMIT |

排名及分数与第二阶段历史报告一致。报价数据会随实际时间过期，当前可用不表示长期可用。

## 5. 第三阶段逐模块核验

| 模块 | 实际实现及接入证据 | 对应源码 | 验收判断 |
| --- | --- | --- | --- |
| A. DeepSeek 客户端 | ChatDeepSeek 异步 transport；环境可配置模型/base_url/超时/重试/token；SecretStr 包装密钥；实际解析时才创建客户端；JSON Output + 重复键/非有限值检查 + Pydantic 校验；识别空内容、截断、非法 JSON/schema、401/403、402、429、5xx、连接及超时；关闭 SDK 隐式重试，由 JSONModel 统一有限重试 | `llm/client.py`、`core/config.py` | **实现已接入，线上未验证**。SDK 请求构造与响应解析只通过 MockTransport 验证。 |
| B. 需求解析 | 草稿字段覆盖型号、厂家、数量、交期、单价/总预算、币种、资质、偏好；人民币用 Decimal 转分；保留原文片段与用户确认来源；缺失/歧义形成问题，不支持硬条件可阻断；默认值单独记录 | `llm/parser.py`、`schemas/agent.py`、`schemas/requirement.py` | **部分完成**。已实现机制，但存在负数语义校验漏洞、遗漏条件的防护缺口；绝对日期没有按原设计折算。Mock 固定草稿不能证明真实中文提取效果。 |
| C. LangGraph | MatchState 为 TypedDict；实际构建 StateGraph 并 compile；所有指定业务节点及澄清/无匹配/错误分支均已接线；独立 request_id、节点轨迹；复用 MatchingService 的三个业务阶段 | `agent/state.py`、`agent/graph.py`、`agent/nodes.py`、`services/matching.py` | **主流程完成，时限验收有缺口**。没有重复评分实现；数据库耗时不能被总时限及时中断。 |
| D. 证据解释 | 模型只选 allowed_reasons 中的指标与 evidence_ids，必须保留供应商顺序及所有风险；不允许新增自由报价/分数字段；Python 渲染事实；失败或越界回退 template，保留排名、分数、证据和风险 | `llm/explainer.py`、`schemas/agent.py`、`agent/nodes.py` | **离线验收通过**。存在越权供应商/排名/分数/报价/引用/风险/顺序测试；线上解释尚未实测。 |
| E. FastAPI | 保留 `POST /api/v1/matches`；新增 `POST /api/v1/agent/matches`；业务状态 success / needs_clarification / no_match / error；响应包含 request_id、需求/草稿、推荐、解释模式、LLM 调用来源、节点轨迹；缺配置 503、不支持硬条件 422、DB 错误 500、超时 504 | `api/main.py`、`api/routes.py`、`api/agent_routes.py`、`schemas/agent.py` | **主要接口已接入**。实际服务启动、health、结构化接口和缺密钥分支已验证，自然语言成功路径通过离线 HTTP 验证。 |
| F. 测试与真实记录 | parser 单元 30、client 单元 20、workflow 集成 21；有正常、澄清、无结果、模型失败、数据库失败、解释降级、防篡改及 Mock SDK 测试；真实检查脚本存在 | `tests/unit/test_agent_parser.py`、`tests/unit/test_llm_client.py`、`tests/integration/test_agent_workflow.py`、`scripts/check_deepseek.py` | **部分完成**。71 项全部通过，但未覆盖本轮发现的边界；没有找到真实 DeepSeek 成功调用记录。 |

源码路径在本表中相对于 `src/componentmatch/`，测试和 scripts 路径相对于项目根目录。

十个实际图节点：`parse_request`、`validate_request`、`retrieve_candidates`、`filter_candidates`、`score_and_rank`、`explain_results`、`request_clarification`、`build_no_match`、`handle_error`、`finalize_response`。`docs/agent_workflow.mmd` 有对应图，图源码不是空文件。

解析边界说明：Pydantic 拒绝非法字段和数值，来源校验可以发现虚构片段和部分数值不一致；这不等于能保证完整提取所有条件。已有设计文档承认该限制，本次报告也不要求形式化证明任意自然语言都无遗漏，但下列具体反例应加入验收。

## 6. 本轮发现的问题（均未修复业务代码）

### P1-01：原文负数可被“校验”为正数，直接进入推荐

位置：`llm/parser.py:30`、`:34`、`:84`、`:114`。

`number_value()` 与金额正则从字符串内部搜索无符号数字，忽略前导负号。离线注入的草稿将原文 `-1000片` 提取为 `quantity=1000`，并准确引用 `-1000片`；来源校验仍通过，返回 HTTP 200 / success / 三家推荐。原文 `单价不超过-1.2元` 被提取为正 1.2 元时同样通过，结果中预算为 120 分。

这证明“原文数值校验”存在具体漏洞，并非仅是未知的模型语义风险。应拒绝或澄清该类输入，不能静默转正。本复现模拟了模型错误输出，**没有证据表明真实 DeepSeek 已实际输出过这个错误**。

### P1-02：部分硬条件被模型遗漏后仍可返回 success

位置：`llm/parser.py:134`、`:142`；`agent/nodes.py:110`。

在有效需求后附加 `要求原厂授权。`，Mock 模型不返回 unhandled_constraints，工作流继续输出三家推荐。当前额外规则仅覆盖含“必须”等有限写法，不能拦住这个明确的硬条件。

在原“7 天内到货”需求后附加 `必须2026年10月22日之前到货。`，Mock 忽略该绝对日期，工作流仍按 7 天推荐。隔离测试业务时钟为 2026-10-21 上海 12:00，推荐交期为 3/2/6 天，不符合追加的日期要求。

此外，`docs/requirements.md` 约定绝对日期按业务时钟折算自然日；当前 Prompt 明确要求绝对日期澄清，归一化代码没有日期转换。这是设计与实现差异，即便模型正确遵循 Prompt，也未实现原定日期能力。应补齐已约定行为，或明确缩小支持范围并同步契约；不要宣称已经支持。

这两项是**模型遗漏的故障注入**，不能用来推断真实模型的发生概率。建议把这些明确硬条件和冲突场景纳入测试，并在前端接入前明确用户确认需求的边界。

### P2-01：Agent 总时限不是整个工作流的严格时限

位置：`agent/graph.py:76`、`agent/nodes.py:29`、`:133`。

模型调用有 asyncio 超时和剩余预算；但图只在部分节点进入时检查 deadline。`await asyncio.to_thread(self.matching.prepare, ...)` 没有等待超时，数据库步骤返回后才由下一节点报错。

离线将 Agent 总预算设为 0.05 秒，将 prepare 延迟 0.3 秒，实际约 **0.359 秒**后才返回 504 / AGENT_TIMEOUT。现有测试验证模型调用超时与预算区分，未验证慢数据库阶段。应补齐数据库等待/图执行的总预算处理与测试；不应将现实现宣传为严格 90 秒响应上限。

### P2-02：静态质量门禁未通过

`ruff check` 退出 1，共 3 个错误：

- `src/componentmatch/agent/nodes.py:3`：I001；`:19`：E501（113 > 100）。
- `tests/conftest.py:3`：I001。

`ruff format --check` 退出 1：`agent/nodes.py`、`schemas/agent.py` 两个文件需要格式化，另 51 个文件已符合格式。

未执行 `--fix` 或写入式 formatter，因为本轮仅审查与环境恢复。

### P2-03：交付文档与真实代码状态明显不一致

README、requirements、architecture、development_plan、tests/README、scripts/README 等仍宣称模型/图尚未实现；实际已有完整代码及测试。`phase2_verification.md` 属于历史记录，应保留其历史语义，不把它伪改为第三阶段验收。`/health` 的 stage 仍为 `deterministic_matching`，只能说明存活，不能用于推断第三阶段完成度。

本次仅新增审查报告，没有代为更新这些设计与交付文档。

### 验收证据缺口：没有真实 DeepSeek 成功记录

`scripts/check_deepseek.py` 是真实调用入口，具备缺密钥跳过、单次调用、token/耗时记录；但**存在脚本不等于执行成功**。仓库中的 `agent_response.mock.json` 明确标注 mock，SDK 兼容性测试使用 `httpx.MockTransport`，本轮完整流程使用 `FakeTransport`。

该脚本只覆盖一次真实解析，不能独自证明“解析 + 数据库 + 评分 + 解释 + HTTP”的真实全链路验收。本机没有密钥，本轮没有执行该脚本或任何付费调用。

## 7. 实际测试与命令记录

以下命令均从项目根目录运行。`logs/phase3_audit/` 保留原始输出；pytest 同时保留 JUnit XML。退出码来自真实进程，不将检查输出推断为成功。

| 实际执行命令 | 退出码 | 实际结果 |
| --- | ---: | --- |
| `python --version` | 0 | 系统 Python 3.13.9 |
| `uv --version` | 0 | uv 0.11.18 |
| `uv --cache-dir .uv-cache sync --locked` | 0 | 新建本机 3.11.15 环境，安装 83 个包 |
| `uv --cache-dir .uv-cache lock --check` | 0 | Resolved 85 packages；锁文件有效 |
| `uv --cache-dir .uv-cache pip check` | 0 | Checked 83 packages；依赖兼容 |
| `uv --cache-dir .uv-cache run --locked pytest -q --junitxml=logs/phase3_audit/pytest.xml` | 0 | **180 passed in 15.46s**；0 failed、0 skipped、0 errors |
| `uv --cache-dir .uv-cache run --locked ruff check src scripts tests` | 1 | 3 errors：I001 × 2、E501 × 1 |
| `uv --cache-dir .uv-cache run --locked ruff format --check src scripts tests` | 1 | 2 files would be reformatted, 51 files already formatted |
| `uv --cache-dir .uv-cache run --locked python scripts/demo_match.py` | 0 | 三种偏好 success；严格预算 no_match；使用原库及业务时钟 |
| `uv --cache-dir .uv-cache run --locked python scripts/seed_demo.py --database-url sqlite:///./logs/phase3_audit/seed_cli.db`（第一次） | 0 | created，六表数据计数正确 |
| 同上（第二次，顺序执行） | 0 | unchanged，快照未刷新、无重复数据 |
| `uv --cache-dir .uv-cache run --locked python logs/phase3_audit/http_smoke.py` | 0 | 实际启动 Uvicorn 并完成 localhost HTTP 探测，结束后停止本轮子进程 |
| `uv --cache-dir .uv-cache run --locked python logs/phase3_audit/offline_probes.py` | 0 | Mock HTTP 正常链路通过；5 项边界探测记录了本报告的 3 类功能缺口 |
| `git rev-parse --verify HEAD` | 128 | 无有效 HEAD；仅检查，没有提交 |

另执行了 `uv ... run --locked python -` 的只读清点脚本（退出 0），结果保留为 `inventory.txt`：统计 pytest XML、六表行数、完整性/FK、元信息、配置变量名称及密钥存在性；没有打印密钥。旧解释器的启动失败是恢复前的真实诊断结果，但初次批量检查未单独捕获该子命令退出码，因此不虚构它的数字退出码。

专项探测脚本退出 0 只代表“复现与记录完成”，**不代表发现的问题已通过验收**。其 5 项反例不计入项目 pytest 的 180 项，也未新增到业务测试套件。

### 测试数量与历史 109 项对比

| 测试文件 | 当前收集并通过的用例数 | 归属 |
| --- | ---: | --- |
| tests/unit/test_contracts.py | 35 | 第二阶段 |
| tests/unit/test_constraints.py | 24 | 第二阶段 |
| tests/unit/test_scoring.py | 11 | 第二阶段 |
| tests/integration/test_database.py | 14 | 第二阶段 |
| tests/integration/test_matching.py | 23 | 第二阶段 |
| tests/integration/test_api.py | 2 | 第二阶段 |
| 第二阶段小计 | **109** | 与历史记录数量相同，本轮全部通过 |
| tests/unit/test_agent_parser.py | 30 | 第三阶段 |
| tests/unit/test_llm_client.py | 20 | 第三阶段 |
| tests/integration/test_agent_workflow.py | 21 | 第三阶段 |
| 第三阶段小计 | **71** | 本轮全部通过，均为离线测试 |
| 合计 | **180** | 单元 120 + 集成 60 |

数量按 pytest 参数化后的实际 testcase 统计，不是函数数量。历史报告为 `109 passed in 1.96s`，本轮为全量 `180 passed in 15.46s`；两者环境和测试范围不同，不做耗时性能比较。由于没有可用提交历史，只能对比当前原阶段测试文件及历史记录，不能证明旧机文件与现文件逐字一致。

### FastAPI 实际运行与离线完整流程

审查脚本实际启动的命令为：

```powershell
.venv\Scripts\python.exe -m uvicorn componentmatch.api.main:app --host 127.0.0.1 --port 55770
```

端口由脚本临时选择，执行命令完整记录在 `http_smoke.txt`；服务确实监听 localhost，不只是 TestClient 导入。输出 `Application startup complete`。结果：

- `GET /health` → 200，`{"status":"ok","stage":"deterministic_matching","version":"0.1.0"}`。
- `GET /openapi.json` → 200，包含 health、原结构化 API、新自然语言 API。
- `POST /api/v1/matches` → 200 / success，供应商顺序 2、3、1。
- `POST /api/v1/agent/matches`（无密钥，真实应用依赖）→ 503 / error / CONFIG_MISSING，带 request_id，没有伪造结果。子进程显式移除了密钥变量，确保此探测不会调用付费服务。

随后通过 TestClient 注入 **FakeTransport**，使用实际编译图、实际 MatchingService、隔离六表数据库和显式测试时钟完成自然语言接口闭环：

```text
parse_request → validate_request → retrieve_candidates → filter_candidates
→ score_and_rank → explain_results → finalize_response
```

返回 200 / success，质量优先排序为 DEMO 02（84.500000）、03（78.893617）、01（54.680851），推荐对象与直接调用 MatchingService.match() 完全相等。`explanation_mode=llm` 表示经过模型接口组织解释，**此次传输来源为 mock**：两个调用均 `source=mock`，`model_name=test-only-fake`，不是 DeepSeek 真实调用成功。完整结果保存在 `mock_http_response.json`。

现有集成测试还验证澄清、无匹配、解析失败、数据库失败、解释降级和评分/排名/风险不可由模型篡改。没有前端测试；本轮不声称全产品验收完成。

## 8. 本轮实际变更与证据保存

- 保留旧环境为 `.venv.migration-backup-20261021/`，按锁文件新建 `.venv/`，恢复工具和依赖缓存。
- 新增本报告与 `logs/phase3_audit/` 的审查输出、HTTP 探测脚本、离线复现脚本、隔离测试库；运行测试产生正常缓存。
- 执行前后 SHA256 比较：现有 src/scripts/tests 的 Python 文件、README、pyproject.toml、uv.lock 和原 `data/componentmatch.db` 的变更数为 **0**。
- 未创建或覆盖 `.env`；未修改现有设计、评分、数据库、Agent、API 或测试实现；未提交 Git；原文件未删除。

关键本地证据文件：`pytest.txt`、`pytest.xml`、`ruff_check.txt`、`ruff_format.txt`、`inventory.txt`、`demo_match.txt`、`seed_created.txt`、`seed_unchanged.txt`、`uvicorn.txt`、`http_smoke.txt`、`offline_probes.txt`、`mock_http_response.json`。这些日志在被忽略的 logs 目录中，是本机审查附件，不能假定会随 Git 自动分发。

## 9. 进入第四阶段前必须补齐的工作

| 优先级 | 任务 | 完成标准 |
| --- | --- | --- |
| P1 | 修复原文数值符号与金额语义校验，补负数量、负预算等反例测试 | 错误模型提取不能将负值静默转正并返回推荐；应明确拒绝或澄清 |
| P1 | 补齐明确硬条件遗漏/冲突的防护与测试，确定绝对日期行为 | 本报告的授权条件和日期反例不得继续无提示 success；日期实现与文档一致；明确解析结果需要用户核对的边界 |
| P1（验收条件） | 用户配置密钥并另行确认后，进行真实 DeepSeek 验证 | 记录真实模型名、JSON/Pydantic 结果、耗时、重试与 token；至少验证解析及正常完整链路的解释，不用 Mock 或缺密钥 skipped 作为成功证据 |
| P2 | 完善数据库/图执行的总时限与异常测试 | 慢数据库等非模型阶段不会无限拖过请求预算；错误类型、响应时限及解释降级策略有清晰一致的约定 |
| P2 | 修正 Ruff 导入/行宽与格式问题 | ruff check、ruff format --check 全部退出 0 |
| P2 | 同步 README、阶段编号、架构/API/配置/测试说明，补第三阶段验收记录 | 新同事可按文档复现现有功能；清楚区分已实现、Mock 验证、真实验证与未实现前端；保留第二阶段历史记录 |
| 最终门禁 | 在以上工作完成后再跑全量回归与 API 冒烟 | 原 109 项无回归、新增边界测试通过、静态检查通过、真实模型证据齐备，再验收第三阶段并启动第四阶段 |

本轮到审查与环境恢复为止。上述任务是后续待办，没有擅自实施；等待用户下一步指令。
