# 第三阶段缺陷修复与最终验证记录

> 历史记录：保留当时的执行日期、测试数字和结论；本机路径已匿名化。当前安装、目录和行为请以 [README](../../README.md) 与 [验证索引](../verification.md) 为准。文中旧命令不作为当前启动指引。

日期：2026-10-21（Asia/Shanghai）。依据：`docs/history/phase3_audit.md` 与本轮用户授权。

## 1. 验收结论

**本轮第三阶段缺陷修复与离线验收：通过。真实 DeepSeek 线上验收：未执行，不能宣称已通过。**

本轮已修复审查发现的数值符号漏洞、明确硬条件遗漏、日期转换/冲突处理，以及数据库等待预算；静态检查全部通过。当前全量 **290 项测试通过**，原有 180 项保留，新增 110 项回归测试。第二阶段评分、权重、排序、数据库定义与种子没有修改，原 109 项回归全部通过。

这里的“通过”限定于本轮要求的代码修复、离线模型及接口验收，不等同于真实模型提取质量、账户权限、模型名称或线上协议兼容性已经验证。如果第三阶段完整验收要求真实模型链路成功，该项仍待用户另行授权执行。

没有开发 Streamlit，没有引入新框架或依赖，没有重构工作流、修改评分业务规则、提交 Git 或调用付费模型。完成本报告后停止。

## 2. 修复结果

| 任务 | 实际修复 | 验收证据 |
| --- | --- | --- |
| P1 数值符号 | 数量与金额解析保留 ASCII、Unicode 正负号及中文“正/负”；负数量、负预算、重复/冲突符号和 ± 不会被转为正数。原文独立扫描防止模型截取不含符号的子串作为证据。数值/单位不一致不得通过；严格价格比较及下限不能被默认为含等号上限。 | 新增符号、负数量、负单价、负总预算、截断依据、符号冲突、数值更改测试；旧反例不再返回推荐。 |
| P1 已知硬条件完整性 | 在进入匹配前复核带单位/数量标签的数量、单价与总预算、元/片表达、ISO9001、TI/厂家标签、明确天数与日期。遗漏或不一致返回澄清；不能靠模型省略字段变成无约束。 | 删除模型草稿中的厂家、型号、数量、预算、资质、交期字段后，相关用例均阻止查询/推荐。 |
| P1 不支持条件 | 原厂授权、授权代理、车规、温度、工作日、非支持证书及币种等已知表达独立检测。原厂授权不能由 ISO9001 代替。 | “要求原厂授权”在模型只返回 ISO9001 时，仍返回 422 / UNSUPPORTED_CONSTRAINT，无推荐。 |
| P1 明确日期 | Python 读取原文日期并按业务时间转换；模型不自行计算天数。处理过去/无效日期、无年份、时区、多个日期、天数冲突与交期不限冲突。日期遗漏也不能直接推荐。 | 日期正例、时区等价、上海/UTC 日期差、非法偏移、日期冲突、跨午夜及完整图测试通过。 |
| P2 超时 | 数据库 prepare 的等待使用 asyncio.timeout，按剩余预算取消等待；业务节点执行前后检查预算，迟到的同步评分结果被丢弃，不再调用解释模型。 | 被阻塞的工作线程释放前，工作流已经返回 504；同步评分超时无推荐；模型调用原超时测试继续通过。 |
| P2 规范 | 修复 I001、E501 并格式化相关代码。 | ruff check 与 ruff format --check 均退出 0。 |
| P2 文档 | README、需求、架构、开发计划、测试/脚本说明同步到实际第三阶段；第二阶段历史记录和第三阶段原审查报告保留。 | 不再把已经实现的客户端、图、解释和自然语言 API 写成未实现。 |

### 日期与确认语义

- 日期支持 `YYYY-MM-DD`、`YYYY/MM/DD`、`YYYY年M月D日`，使用 Asia/Shanghai 业务日期。裸日期、“不晚于”和“当天”包含该日；“之前/以前/前”不包含该日。
- 日期到天数为截止日减业务日期，允许 0 表示当天；过去日期返回澄清。
- ISO 具体时刻必须有 `Z` 或 `±HH:MM`。转换到 UTC 后，将剩余时间按完整 24 小时向下取整，避免放宽截止时刻。“之前”在恰好整天边界再减一天。
- 无时区时刻、时区名称、非法偏移、部分时间格式、日期下限及非 ISO 中文时刻要求澄清，不猜测时区或把下限当上限。
- 多个不同截止条件、日期与明确天数不一致、日期与交期不限冲突时，不自行选择一项；需要用户更正原文或确认条件。
- 图开始时捕获业务时间，检索后用 MatchingService 的实际业务时间复核；如跨上海午夜导致转换结果变化，重新澄清，不用旧天数继续评分。未改动 MatchingService 的业务时钟规则。
- `confirmed_fields` 仍是显式用户确认，按字段覆盖解析值；不能取消检测到的无法验证条件。不能把模型给出的值当成用户确认。

## 3. 原审查反例的修复前后

原脚本保留在 `logs/phase3_audit/`；本轮复制到 `logs/phase3_final/` 重新运行，未覆盖原审查证据。下表均为 Mock 故障注入，不代表真实 DeepSeek 曾发生这些错误。

| 原反例 | 审查时 | 修复后实际结果 |
| --- | --- | --- |
| 原文 -1000 片，模型输出 +1000 并引用 -1000 片 | 200 success，三家推荐 | 503 error / LLM_EVIDENCE_INVALID，无推荐 |
| 原文单价不超过 -1.2 元，模型输出正 1.2 元 | 200 success | 200 needs_clarification，明确负预算问题，无推荐 |
| 在 7 天需求后追加明确截止日期，模型遗漏日期 | 200 success | 200 needs_clarification，日期与天数冲突，无推荐 |
| “要求原厂授权”，模型遗漏该条件 | 200 success | 422 error / UNSUPPORTED_CONSTRAINT，无推荐 |
| 预算 0.05 秒，prepare 延迟 0.3 秒 | 约 0.359 秒后才返回超时 | 工作流约 0.063 秒返回 504 / AGENT_TIMEOUT，未进入过滤；线程仍可继续结束只读操作 |

0.063 秒是这一次执行的观测值，不是严格 SLA。Windows 定时器精度、调度及收尾有开销。新的事件阻塞测试直接证明“工作线程尚未释放时已返回”，不依赖某个很窄的计时阈值。

## 4. 实际执行命令与结果

工作目录为项目根目录；工具版本沿用锁定环境，Python 3.11.15。原始输出保存在 `logs/phase3_final/`。

| 命令 | 退出码 | 最终输出/结果 |
| --- | ---: | --- |
| `uv --cache-dir .uv-cache run --locked pytest -q --junitxml=logs/phase3_final/pytest.xml` | 0 | **290 passed in 7.17s**；无失败、跳过或错误 |
| `uv --cache-dir .uv-cache run --locked ruff check src scripts tests` | 0 | All checks passed! |
| `uv --cache-dir .uv-cache run --locked ruff format --check src scripts tests` | 0 | 55 files already formatted |
| `uv --cache-dir .uv-cache run --locked python scripts/demo_match.py` | 0 | balanced / cost / quality 均 success；严格预算 no_match |
| `uv --cache-dir .uv-cache run --locked python logs/phase3_final/http_smoke.py` | 0 | 实际 Uvicorn 启动、health、结构化 API 和缺配置自然语言 API 检查成功 |
| `uv --cache-dir .uv-cache run --locked python logs/phase3_final/offline_probes.py` | 0 | Mock HTTP 全流程成功、原审查反例按预期被阻断、数据库等待超时生效 |

开发中的检查过程：先对原解析/图测试运行 51 项，通过；首批新回归 90 项通过；首次 `ruff check --fix` 修复导入后仍报告 5 个 E501，随后 formatter 解决；中间全量 283 项、286 项分别通过。边界复核补充后得到上述最终 290 项。本报告没有把中间结果当成最终数量。

### 测试数量

| 文件/范围 | 通过数量 |
| --- | ---: |
| 原第二阶段：contracts / constraints / scoring / database / matching / api | **109**（35 / 24 / 11 / 14 / 23 / 2） |
| 原第三阶段：test_agent_parser.py | 30 |
| 原第三阶段：test_llm_client.py | 20 |
| 原第三阶段：test_agent_workflow.py | 21 |
| 新增 test_parser_regressions.py | **92** |
| 新增 test_agent_regressions.py | **18** |
| 总计 | **290 = 原 180 + 新增 110** |

pytest 的数量按参数化后的实际 testcase 统计。独立审查探测脚本不计入 290 项。

## 5. API 与完整流程验证

实际启动命令（端口由脚本临时选择）：

```powershell
.venv\Scripts\python.exe -m uvicorn componentmatch.api.main:app --host 127.0.0.1 --port 58757
```

Uvicorn 输出 Application startup complete。验证结束后停止本轮启动的进程，没有留下后台服务。

| 路径/场景 | 实际结果 |
| --- | --- |
| GET /health | 200，status=ok；保留原 stage=deterministic_matching 以兼容原接口，该字段只代表历史存活标签 |
| GET /openapi.json | 200，包含两个匹配端点及 health |
| POST /api/v1/matches | 200 success，供应商顺序 2、3、1 |
| POST /api/v1/agent/matches，真实应用依赖但没有进程密钥 | 503 error / CONFIG_MISSING，带 request_id，无伪造结果 |
| Agent HTTP，注入 Mock 模型 | success / needs_clarification / no_match / error 分支通过；解释失败保留评分并返回 template |
| 完整 Mock 图 | parse → validate → retrieve → filter → score_and_rank → explain → finalize；与 MatchingService.match() 推荐对象完全一致 |

服务启动探测的子进程显式移除 DEEPSEEK_API_KEY，不加载环境文件；保证此探测不会发起真实模型调用。成功自然语言流程使用实际 FastAPI/TestClient、编译图、数据库、匹配服务和显式 FakeTransport，并非伪造整个 HTTP 响应。

完整 Mock 成功结果：质量优先排名为 DEMO 02 / 84.500000，DEMO 03 / 78.893617，DEMO 01 / 54.680851。响应有 request_id、结构化需求、证据、推荐、风险和解释；`explanation_mode=llm`，但两个 `llm_calls[].source` 都为 `mock`，模型名 `test-only-fake`。**这不是 DeepSeek 真实调用成功。**

## 6. 第二阶段无回归证据

原 `scoring/`、`models/`、`db/`、`services/` 目录中的代码内容经 SHA256 比较未变化；pyproject.toml、uv.lock、原 data/componentmatch.db 也未变化。没有调整权重、归一化、时效、Top 3 或表字段来使测试通过。

本次真实业务时钟演示：`2026-10-21T15:12:33Z`（上海 23:12:33）；数据库仍使用原快照，未回拨时钟。

| 偏好 | 第 1 名 | 第 2 名 | 第 3 名 |
| --- | --- | --- | --- |
| balanced | 02 / 83.500000 | 03 / 80.226950 | 01 / 60.680851 |
| cost | 01 / 73.180851 | 03 / 70.893617 | 02 / 67.000000 |
| quality | 02 / 84.500000 | 03 / 78.893617 | 01 / 54.680851 |

严格单价上限 1 分时返回 no_match，13 条报价触发 UNIT_PRICE_OVER_LIMIT。与第二阶段历史结果一致。数据仍为虚构 DEMO，并会随实际时间自然过期。

## 7. 修改文件

| 文件 | 修改内容 |
| --- | --- |
| src/componentmatch/llm/parser.py | 符号解析、来源单位检查、已知条件完整性检查、日期换算/冲突、Prompt 同步 |
| src/componentmatch/agent/state.py | 保存本次解释原文使用的业务时间 |
| src/componentmatch/agent/graph.py | 从匹配服务的测试时钟或实际时间捕获业务时间；图结构不变 |
| src/componentmatch/agent/nodes.py | 日期上下文、检索后时钟复核、数据库等待预算、节点执行后预算检查；修复格式 |
| src/componentmatch/core/config.py | 仅修正过时类说明，不改配置字段/default |
| src/componentmatch/schemas/agent.py | 仅格式化，不改契约规则 |
| tests/conftest.py | 仅导入排序；临时库/网络阻断策略不变 |
| tests/unit/test_parser_regressions.py | 新增 92 项符号、完整性、日期/时区和语义回归 |
| tests/integration/test_agent_regressions.py | 新增 18 项图/HTTP、无查询阻断、排名不变、跨午夜及超时回归 |
| README.md | 同步第三阶段状态、自然语言接口、配置、限制和验证入口 |
| docs/requirements.md | 更新当前契约、支持的原文检查范围、日期/时区和确认语义 |
| docs/architecture.md | 同步真实状态字段、节点行为、解释契约、错误码和协作式超时边界 |
| docs/development_plan.md | 统一四阶段编号，保留真实模型和前端后续边界 |
| docs/database_design.md、docs/scoring_design.md | 仅同步测试状态表述，不修改数据库或评分设计 |
| tests/README.md、scripts/README.md | 更新离线测试、审查回归与真实模型脚本边界 |
| docs/phase3_final_verification.md | 本报告 |

本轮执行材料位于被 Git 忽略的 logs/phase3_final/；其中包括 pytest XML/输出、Ruff 输出、实际服务日志、Mock 完整响应、审查复现脚本及隔离测试数据库。历史 docs/phase2_verification.md、docs/phase3_audit.md 及原审查日志保持原样，不改写历史结果。

## 8. 仍存在的限制与配置观察

1. **自然语言完整性是有限词法检查。** 支持的具体模式见需求文档；同义词、嵌套否定、复杂上下文、未识别的行业条件等可能遗漏或产生保守误报。不能宣称识别任意自然语言中的全部硬条件。用户必须核对结构化需求，无法核对的条件应使用明确表达或结构化确认。
2. **同步操作不能严格强制中断。** asyncio 超时停止数据库等待，已经启动的线程仍可能继续执行只读查询；会话在其原有上下文结束时关闭。同步 CPU 校验/过滤/评分只能事后丢弃迟到结果，事件循环调度和收尾也有开销。因此不承诺严格 90 秒墙钟上限。未引入分布式任务、异步数据库或生产并发治理。
3. **解释阶段保留原降级语义。** 已有有效评分后，模型解释超时/失败返回 Python 模板及 success，不将其改成无结果；故障信息和来源可见。
4. **真实 DeepSeek 尚未验证。** 本轮进程中没有配置 API Key，.env 不存在；但 .env.example 中检测到非空疑似凭据，不能继续沿用原审查“所有位置都没有密钥”的结论。该值的有效性、权限、余额均未探测，未加载、未使用、未修改，真实调用数为 0。
5. **凭据处理提醒。** 首次读取 .env.example 时非空凭据进入了工具输出，已告知用户；本报告及新生成日志不复述该值。建议轮换，再迁移到不提交的 .env 并清空配置示例；本轮没有擅自覆盖用户配置。后续真实调用仍需明确授权。
6. **日期支持有明确范围。** 相对日期、无年份、时区名称、非 ISO 时刻和冲突条件需要澄清。精确时刻保守折算到整天，可能排除只能以更细时间粒度描述的报价；数据库仍只表示整数交期，没有扩展结构。
7. **模型质量、生产 SLA 和前端不在离线证明范围。** 未执行真实解析/解释链路，未做生产压力测试，未开发或验收 Streamlit。

第三阶段本轮代码修复和离线验收已完成。完整真实模型验收仍是独立待办，不以 Mock 替代；等待用户下一步指令。
