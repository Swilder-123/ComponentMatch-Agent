# DeepSeek 真实联调验收记录

> 历史记录：保留当时的执行日期、测试数字和结论；本机路径已匿名化。当前安装、目录和行为请以 [README](../../README.md) 与 [验证索引](../verification.md) 为准。文中旧命令不作为当前启动指引。

执行时间：2026-10-21 23:35:23 起（Asia/Shanghai；UTC 15:35:23）。

**结论：本次三个指定场景的真实 DeepSeek 联调全部通过。**
此前离线验收与本次真实联调共同满足第三阶段既定验收范围，可进入另行安排的第四阶段。
这不代表任意自然语言输入、生产可用性或真实供应商数据已经验收。

## 授权与执行边界

- 用户确认密钥已轮换，随后明确指示“测试，我已经写了”，授权本轮执行。
- 从本地 `.env` 注入配置；未输出、复制或提交密钥，未修改 `.env`。
- 复用现有 `scripts/check_deepseek.py`，只执行一轮，最多四次模型调用尝试、无重试。
- 实际使用 `LimitedDeepSeekTransport` → `DeepSeekTransport` → `ChatDeepSeek`，
  直连 `https://api.deepseek.com`，配置模型 `deepseek-flash`，没有使用 Mock。
- 使用原有编译后的 AgentWorkflow、MatchingService 和现有 SQLite DEMO 数据。
- 真实服务商响应通过 JSON 解码、Pydantic Schema、原文/证据及业务结果校验。

实际执行命令：

```powershell
uv --cache-dir .uv-cache run --locked --env-file .env python scripts/check_deepseek.py --allow-paid-api > logs/deepseek_live_result.json
```

**退出码：0。** 报告 `mode=live`、`status=passed`、`compatibility_verified=true`、
`transport_attempts=4`。应用层和 SDK 层均无重试。
模型调用超时配置 20 秒，Agent 预算 90 秒，单次最大输出 4096 token。

## 场景结果

| 场景 | 输入 | 实际状态 | 解释模式 | 模型调用数 | 工作流耗时 |
|---|---|---|---|---:|---:|
| 正常匹配 | 采购TI的LM358DR，1000片，7天内到货，单价不超过1.2元，总预算不超过1200元，必须ISO9001，质量优先。 | success | llm | 2 | 4.359 秒 |
| 信息缺失 | 采购TI的LM358DR | needs_clarification | none | 1 | 1.109 秒 |
| 无匹配 | 同正常输入，单价上限改为 1 分 | no_match | none | 1 | 1.297 秒 |

三个工作流返回码均为 200；这是工作流供 FastAPI 使用的返回码，不是本轮另启服务器测得的
HTTP 网络结果。本次是实际服务商加进程内完整工作流联调，未进行部署或 HTTP 压测。

场景工作流耗时合计 **6.765 秒**。包含 Python/依赖启动和本地预检查的执行工具墙钟约 9.47 秒，
两者计时范围不同。

## 逐项校验

全部场景的 Schema、UUID request_id、状态、DEMO 标识、原文引用、模型来源、调用阶段和
无重试校验通过；所有模型调用 outcome 均为 success，没有错误码。

- 正常匹配：结构化需求与预期一致，数量 1000、7 天、单价上限 120 分、总预算 120000 分、
  ISO9001、质量优先均正确。Top 3 完整推荐对象与实际 MatchingService 结果一致，
  包括排序、总分、分项、报价、证据、风险；排除统计、警示、规则版本、权重、数据快照和
  业务日期一致。真实 LLM 解释成功，未触发 Python 模板降级；解释证据有效、风险文案完整。
- 信息缺失：数量与交期未被擅自补全，返回澄清问题，不返回推荐或解释，仅调用一次解析。
- 无匹配：正确保留 1 分单价上限及其他约束；实际检索到报价并排除不合格报价，
  返回 no_match。排除结果及警示与 MatchingService 一致，没有放宽预算或生成推荐。

## 调用与 token 记录

| 场景/阶段 | 模型 | 耗时 | 输入 token | 输出 token | 结果 |
|---|---|---:|---:|---:|---|
| 正常/解析 | deepseek-flash | 2234 ms | 1499 | 210 | success |
| 正常/解释 | deepseek-flash | 2109 ms | 1709 | 519 | success |
| 缺失/解析 | deepseek-flash | 1109 ms | 1467 | 108 | success |
| 无匹配/解析 | deepseek-flash | 1266 ms | 1497 | 204 | success |
| 合计 | — | — | **6172** | **1041** | **4 次成功** |

token 来自客户端收到的 usage 元数据；实际货币费用以服务商账单为准，未编造费用。
模型名记录为配置/API 使用的别名，没有额外调用服务商查询实际底层模型版本。

## 文件证据与完整性

- `logs/deepseek_live_result.json`：三个场景与全部检查、调用/usage 安全摘要。
- `logs/deepseek_live_execution.json`：实际命令与退出码。
- `logs/deepseek_live_integrity_before.json`、`logs/deepseek_live_integrity.json`：
  38 个源码、数据库、依赖文件的 SHA-256 前后相同，changed_files 为空。
- 检查报告不包含当前配置的密钥值；未存储原始模型文本、提示词或原始异常正文。
- 本轮未修改业务代码、评分规则、数据库或 LangGraph 主流程，未提交 Git，未开发 Streamlit。

此前准备阶段的离线测试为 **303 passed**，Ruff 检查及格式检查通过，记录见
`docs/history/deepseek_live_preparation.md`。本轮未重复运行这些离线检查，也未将它们计为真实调用。

## 验收边界

本轮真实联调完成，未追加调用。可将第三阶段标记为“离线与指定真实场景验收通过”。
仍使用 DEMO 供应商数据；三个场景不能证明任意自然语言表达都不会遗漏条件。
同步数据库工作线程超时后可能继续只读操作，仍不能保证严格总墙钟时限。
如需更多真实场景或稳定性测试，应另行确定调用预算；本轮到此停止，等待下一步指令。
