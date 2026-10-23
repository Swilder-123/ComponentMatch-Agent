# Streamlit AI 单入口调整验证

> 历史记录：保留当时的执行日期、测试数字和结论；本机路径已匿名化。当前安装、目录和行为请以 [README](../../README.md) 与 [验证索引](../verification.md) 为准。文中旧命令不作为当前启动指引。

日期：2026-10-22（北京时间）。

**结论：本轮验收通过。** 前端仅保留自然语言采购输入和五个业务案例，所有业务提交统一请求
`POST /api/v1/agent/matches`。后端结构化API、MatchingService及确定性评分完整保留。

## 修改内容

- `frontend/app.py`：移除运行模式控件、结构化参数表单、金额输入转换、规则请求队列及相关状态/分支。
  保留原文输入、澄清补充、错误与无匹配、证据模板降级、实际模型来源、节点轨迹和风险证据。
- `frontend/api_client.py`：移除前端结构化请求方法和相关契约导入，仅校验Agent业务响应；健康检查仍可用。
- `frontend/presentation.py`：删除模式选项；中文字段/风险/单位、默认项、横向五维图及证据转换保持不变。
- `scripts/start_demo.py`：启动提示同步为自然语言提交可能产生模型API费用；启动不调用模型。
- `tests/integration/test_phase5_modes.py`：保留三档偏好的后端结构化接口测试，直接使用FastAPI TestClient，
  不依赖已移除的前端方法；移除规则表单和模式切换专用测试。
- `tests/unit/test_phase5_presentation.py`：清理已删除的前端金额输入转换测试；保留中文、单位及图表测试。
- `tests/integration/test_streamlit_app.py`：增加唯一自然语言入口/无规则状态、Mock与模板来源标记检查；
  所有Mock HTTP交互均断言请求路径为Agent API。
- `tests/phase5_browser_check.py`、`tests/phase5_local_check.py`：复用浏览器验收，检查唯一入口和页面请求路径；
  将本轮日志写入 `logs/ai_only/`，保留此前验收材料。
- `README.md`、`frontend/README.md`、`tests/README.md`、`docs/demo_guide.md`：更新当前入口、费用边界和演示步骤。
  `docs/history/final_acceptance.md`标明是历史记录，原377项结果没有改写为当前结果。

没有修改后端代码、数据库结构或数据、评分公式和权重、LangGraph主流程、依赖锁文件或`.env`。
开始/结束对39个受保护文件进行SHA256对比，变化0；包含全部`src/` Python源码、现有SQLite、
pyproject、uv.lock和`.env`，记录见 `logs/ai_only/integrity.json`。

## 实测结果

| 命令/检查 | 退出码 | 结果 |
|---|---:|---|
| `uv --cache-dir .uv-cache run --locked pytest -q --junitxml=logs/ai_only/pytest.xml` | 0 | **359 passed in 20.03s** |
| `.venv\Scripts\ruff.exe check src scripts tests frontend` | 0 | All checks passed |
| `.venv\Scripts\ruff.exe format --check src scripts tests frontend` | 0 | 71 files already formatted |
| `uv --cache-dir .uv-cache lock --check` | 0 | 锁文件检查通过 |
| `.venv\Scripts\python.exe -m tests.phase5_local_check` | 0 | 本地HTTP及13项桌面/窄屏浏览器检查通过 |
| `.\scripts\start_demo.ps1 -SmokeTest -ApiPort 18011 -UiPort 18511` | 0 | FastAPI/Streamlit健康检查、启动和关闭通过 |

测试数由377变为359：删除20项仅服务于已移除前端功能的测试（9项金额输入、11项规则UI/客户端），
新增2项AI单入口及来源显示测试。原后端测试保留，三档结构化路由回归调整为直接调用后端；
没有通过跳过或削弱后端业务测试消除失败。

首次执行有1项新增测试失败：错误使用了本机AppTest不公开的`filtered_state`属性，
按已安装版本改用`session_state.keys()`后全量复跑通过；未改业务逻辑掩盖测试错误。

## 本地HTTP与视觉验证

实际本地Chrome → Streamlit 18510 → FastAPI 18010 → 原工作流/服务 → 现有DEMO数据库。
业务时钟使用当前系统时间，没有刷新种子、重置数据库或回拨时钟。
模型使用显式Mock，测试后端阻断真实DeepSeek传输；**本轮付费调用0次**。

- 浏览器产生11次业务请求，**全部为 `/api/v1/agent/matches`**，结构化请求0次。
- 另行直接发送6次后端结构化请求，验证综合/成本/质量、严格单价、库存不足和总预算超限；
  这些不是页面入口，结构化路径模型调用均为0。
- 页面初始状态仅一个自然语言需求输入框、五个案例和提交/清空按钮，没有单选模式、模型开关、结构化表单。
- 正常匹配、成本/质量偏好、信息缺失、用户补充、无匹配、模型超时、解释模板降级均通过。
- Mock页面明确标记离线来源；模板显示“证据模板”。没有将其标为真实DeepSeek调用成功。
- 显示后端结构化需求、原文依据、实际node_trace、推荐卡片、中文证据/风险与横向0～100分图表。
- 人工查看1440px桌面及390px窄屏截图，图表中文标签和图例完整，无页面水平溢出。
- 测试退出后18010、18510、18011、18511四个端口均释放，未停止用户已有服务。

证据位于 `logs/ai_only/pytest.xml`、`browser_result.json`、`http_call_audit.json`、
`real_clock_rules.json`、`integrity.json`；截图包括 `initial_ai_only.png`、`desktop_ai_mock.png`、
`evidence_mock.png`、`chart_desktop.png`、`chart_mobile.png`。正常启动日志位于
`logs/demo-20261022-105119-15080/`。

## 使用与剩余限制

如旧版服务仍在运行，请先用原启动终端Ctrl+C关闭，再启动并刷新页面：

```powershell
.\scripts\start_demo.ps1 -ApiPort 8001 -UiPort 8502
```

打开 <http://127.0.0.1:8502>。启动不调用模型；提交需求、重新执行或补充匹配会调用实际配置的DeepSeek，
按授权控制费用。需要澄清时仍会出现补充文本框，这是同一Agent请求的补充机制，不是另一匹配入口。

无已知阻塞本轮验收的问题。真实模型可用性本轮未重新探测，当前网络、账户和模型状态不能用Mock证明；
历史真实验收见 `deepseek_live_verification.md`。原有DEMO数据会自然过期，同步数据库超时和自然语言
有限完整性校验的限制保持不变。仅本机演示，没有部署公网或扩展其他业务功能。
