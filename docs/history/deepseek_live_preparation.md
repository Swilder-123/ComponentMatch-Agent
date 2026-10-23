# DeepSeek 真实联调准备记录

> 历史记录：保留当时的执行日期、测试数字和结论；本机路径已匿名化。当前安装、目录和行为请以 [README](../../README.md) 与 [验证索引](../verification.md) 为准。文中旧命令不作为当前启动指引。

日期：2026-10-21。范围：密钥安全、配置核对、复用联调脚本、离线验证。

**准备工作完成，尚未获得真实调用批准。本轮真实 DeepSeek 调用为 0，线上兼容性尚未验证。**
当前需用户在服务商控制台轮换旧凭据，并在本地 `.env` 填入新密钥。

## 1. 密钥安全检查与处置

- 检查时 `.env` 不存在，进程 `DEEPSEEK_API_KEY` 未配置；非空凭据实际上位于
  `.env.example` 第 3 行。未调用服务商验证该凭据有效性。
- 已先报告风险，再清空模板的 API Key。未复制旧密钥，未生成含密钥的备份。
- 旧凭据曾在此前工作中的工具输出出现；清空文件不能撤销已暴露凭据。
  **请在 [DeepSeek 控制台](https://platform.deepseek.com/) 撤销/轮换旧凭据。**
  本工具无法确认控制台轮换是否完成，也不能清除桌面会话历史。
- 从已清空的模板创建了本地 `.env`，其中 API Key 为空，供用户自行填写。
  没有覆盖已有 `.env`；本轮没有在终端或聊天展示任何凭据。
- `.gitignore` 已包含 `.env`、`.env.*`、`logs/`、`*.log`，并有 `!.env.example` 例外。
  因而模板必须保持空密钥。`git check-ignore` 验证 `.env` 和日志受保护。
- `git ls-files` 返回 0 个已跟踪文件；`git log --all` 无提交记录。未执行 Git 提交。
- 清理前按已配置密钥精确匹配和密钥模式扫描，仅发现模板一处；清理后扫描 124 个文件，
  未发现 DeepSeek 风格密钥、长 Bearer token 或私钥头模式，包含项目源码、文档和日志。
  扫描排除 `.git`、虚拟环境及旧迁移环境、依赖缓存、字节码/格式缓存、符号链接，
  单文件上限 10 MB（本次没有因大小跳过文件）。模式扫描无法证明不存在任何形式的秘密。

安全结果仅包含文件位置、数量和布尔值，保存在 `logs/deepseek_preparation/security.json`。

## 2. 正确的本地配置

`.env.example` 和当前空白 `.env` 使用以下配置。只在本地 `.env` 的等号后填写新密钥，
不要把密钥放进聊天、命令参数、模板、数据库或截图。

```dotenv
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
LLM_TIMEOUT_SECONDS=20
LLM_MAX_RETRIES=1
LLM_MAX_TOKENS=4096
AGENT_TIMEOUT_SECONDS=90
DATABASE_URL=sqlite:///./data/componentmatch.db
```

应用 `Settings` 只读进程环境，不会自动读取 `.env`。使用 `uv run --env-file .env` 显式注入。
联调脚本局部强制 `LLM_MAX_RETRIES=0`，不修改应用默认配置。每次模型调用最多输出 4096 token；
输入 token 和实际计费以服务商记录为准。不要用打印环境变量的方式确认密钥。

## 3. 客户端核对

| 项目 | 实际代码与结论 |
|---|---|
| 客户端 | `src/componentmatch/llm/client.py` 的 `DeepSeekTransport`，通过 `ChatDeepSeek` 发请求 |
| 模型与地址 | 默认 `deepseek-flash`、`https://api.deepseek.com`；当前预检查与默认值一致 |
| 输出模式 | `response_format={"type":"json_object"}`，非流式，thinking disabled |
| JSON 与 Schema | 严格 JSON 解码拒绝重复键和非有限数；Pydantic `RequirementDraft` / `ExplanationPlan` 校验 |
| 业务校验 | 原文来源校验、确定性需求归一化；解释理由只允许实际证据，风险不得删改 |
| 错误 | 超时、认证、余额、限流、空输出、截断、JSON/Schema 错误转为安全错误码 |
| 重试 | SDK 层为 0；脚本也把应用重试设为 0 |
| 配置有效性 | 本地参数与官方文档一致；没有验证账户权限、余额、网络连通性或真实模型响应 |

已查阅官方 [首次调用 API](https://api-docs.deepseek.com/zh-cn/)、
[JSON Output](https://api-docs.deepseek.com/guides/json_mode/) 和
[Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)。
官方当前列出 `deepseek-flash` 与上述地址；JSON Object 模式不等于服务端强制应用 Schema，
所以现有本地 Pydantic 和业务校验仍然必要。官方也提示 JSON 模式可能返回空内容。

## 4. 联调脚本与三个场景

复用 `scripts/check_deepseek.py`。旧脚本仅做一次解析，未覆盖解释和完整工作流，
且手写解析 payload 未包含当前工作流传入的业务时间/时区。
现在直接调用实际 `AgentWorkflow.run()`，复用现有图、数据库、评分、解释和所有校验。
未修改 `src/`、评分规则、数据库结构、数据文件或 LangGraph 主流程。

| 场景 | 实际输入 | 预期结果 | 正常情况下调用次数 |
|---|---|---|---:|
| 正常匹配 | 采购TI的LM358DR，1000片，7天内到货，单价不超过1.2元，总预算不超过1200元，必须ISO9001，质量优先。 | success；Top 3 与 MatchingService 一致；解释模式 llm | 2：解析、解释 |
| 信息缺失 | 采购TI的LM358DR | needs_clarification；缺数量、交期；无推荐和解释 | 1：解析 |
| 无匹配 | 同正常输入，但单价上限改为 1 分 | no_match；报价实际被硬条件排除；不放宽预算 | 1：解析 |

调用边界：

- 默认没有 `--allow-paid-api`，只检查本地配置、数据库和确定性场景，密钥存在也不调用模型。
- 真实模式只接受官方 HTTPS 地址（含 `/v1` 兼容形式）及已核对的模型名。
  脚本禁用环境代理和 HTTP 重定向，避免被静默转到其他网关；需代理的环境可能无法直连。
- 三个场景顺序执行，无重试；任何失败、结果不符或模板解释降级，停止后续场景。
- 脚本传输层对整轮最多放行四次模型调用尝试。即便错误解析导致额外解释分支，也不会无限调用。
  调用尝试不等于服务商收到或计费的请求；拒绝超限也可能生成本地错误记录。
- 只有真实模式的三个场景全部通过才返回 `compatibility_verified=true`。
  缺密钥、未批准、Mock、解释降级均不能算真实验收成功。

逐个响应核验：

- `AgentResult` Schema、UUID request_id、工作流返回状态码、业务状态、DEMO 标识。
- 原文引用、明确字段和预算单位、缺失字段保留、澄清问题。
- 需求与场景预期一致；完整 recommendations 与同一数据源的 MatchingService 结果一致，
  包括顺序、报价、分项和总分、证据、风险；排除原因、统计和警示一致。
- 数据快照、规则版本、权重、业务日期一致；跨日或数据变化导致差异时报告失败，不强行通过。
- 解释证据 ID 必须存在，风险文案原样保留；正常场景必须完成真实 LLM 解释。
- 调用记录来源、模型名、阶段、尝试次数和 outcome 符合预期。

报告仅输出场景名、状态、request_id、模型名、耗时、校验布尔值、解释模式、token 计数和
程序生成的安全错误码。不会输出凭据、原始响应、提示词或异常正文；不推算货币账单。
这属于真实服务商加进程内工作流联调，不是远程部署/HTTP 网络压测；报告中的 http_status
为工作流供 API 使用的返回码。已有离线测试另行覆盖 FastAPI 路由。

## 5. 本轮实际执行结果

| 命令 | 退出码 | 实际结果 |
|---|---:|---|
| `.venv\Scripts\python.exe -m pytest tests/integration/test_deepseek_check_script.py -q` | 0 | 13 passed，1.50s；全部离线 |
| `uv --cache-dir .uv-cache run --locked pytest -q` | 0 | **303 passed，9.11s**：原有 290 + 新增 13 |
| `uv --cache-dir .uv-cache run --locked ruff check src scripts tests` | 0 | All checks passed |
| `uv --cache-dir .uv-cache run --locked ruff format --check src scripts tests` | 0 | 56 files already formatted |
| `uv --cache-dir .uv-cache run --locked --env-file .env python scripts/check_deepseek.py` | 0 | needs_configuration；本地数据库检查全部通过；transport_attempts=0；compatibility_verified=false |

预检查退出码 0 表示本地检查正常结束，**不表示已配置密钥或真实 API 成功**。
正常场景能在本机 DEMO 数据中得到 Top 3；严格预算场景确实检索到报价并得到 no_match。
未刷新数据库、伪造业务时钟或改变规则来满足场景。

新增测试覆盖默认零调用、无密钥、地址/模型白名单、异常脱敏、三个离线工作流场景、
Mock 不得算真实成功、模板降级不得算完整成功、第五次调用被拦截、失败后停止。
这些测试的 Mock 只用于测试脚本的保护与校验能力，全部受测试套件的外部网络禁用约束。
从未把 Mock 返回值记录为真实模型成功。

证据：`logs/deepseek_preparation/{pytest,ruff_check,ruff_format,preflight,security,integrity}.json`。
38 个受保护源码/数据库/依赖文件的 SHA-256 前后相同；未提交 Git。

## 6. 修改文件及后续操作

修改：`.env.example`、`scripts/check_deepseek.py`、`scripts/README.md`、`README.md`、
`docs/development_plan.md`。
新增：空白本地 `.env`（被忽略）、`tests/integration/test_deepseek_check_script.py`、本准备记录，
以及被忽略的 `logs/deepseek_preparation/` 验证证据。未开发前端。

用户操作：

1. 在服务商控制台轮换旧凭据；本地编辑 `.env` 填入新密钥，保持 `.env.example` 密钥为空。
2. 在项目根目录执行下面的零调用预检查：

   ```powershell
   uv --cache-dir .uv-cache run --locked --env-file .env python scripts/check_deepseek.py
   ```

   应显示 key_present=true、local_checks_passed=true、status=awaiting_approval、
   transport_attempts=0、compatibility_verified=false。key_present 只证明已填值，不证明有效。

3. 确认后明确批准三个真实场景（deepseek-flash、最多四次模型调用尝试、无重试）。
   **获得批准前，不执行下一条命令。** 获批后使用：

   ```powershell
   uv --cache-dir .uv-cache run --locked --env-file .env python scripts/check_deepseek.py --allow-paid-api > logs/deepseek_live_result.json
   ```

   真实失败会停止，不自动重试、不切换模型、不换 Mock。后续基于实际报告决定是否重新批准。

仍存限制：账户与在线服务未验证；仅覆盖三个指定自然语言场景，无法证明任意表达无遗漏；
数据库仍为虚构 DEMO 供应商数据。同步数据库工作线程超时后可能继续完成只读操作，
不能宣称严格墙钟总时限；token 使用记录不能代替服务商账单。

**本轮到此停止，等待用户填写配置及明确批准真实测试。**
