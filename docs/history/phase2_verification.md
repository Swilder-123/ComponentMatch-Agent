# 第二阶段交付与实际验证记录

> 历史记录：保留当时的执行日期、测试数字和结论；本机路径已匿名化。当前安装、目录和行为请以 [README](../../README.md) 与 [验证索引](../verification.md) 为准。文中旧命令不作为当前启动指引。

日期：2026-10-21；环境：Windows / PowerShell，uv 0.11.23，Python 3.11.15。
以下结果来自实际执行，不是预设成功输出。所有业务数据为 DEMO，不代表云汉芯城或任何真实企业。

## 1. 本轮交付与设计调整

- 沿用六张表，未增加、删除或重命名字段。将原设计的类型、外键、唯一键、枚举和数值约束落地。
- 实现内部 `MatchingService.match(ProcurementRequirement)`，不依赖 LLM 或 LangGraph。
- 提供结构化 `POST /api/v1/matches`，不接受 natural_language；保留健康检查，不自动建表。
- 原草案默认权重 P30/D20/Q25/O20/R5 被本轮要求覆盖为 **P20/D25/Q30/O20/R5**。
- 旧预算 scope+amount 尚未实现，本轮输入契约明确改为独立的 max_unit_price_cents、
  total_budget_cents；二者可同时生效，均为人民币分，含税货款、不含运费。
- 默认业务时钟为实际 UTC 时间，按 Asia/Shanghai 解释业务日期；固定时钟只用于显式测试模式。
  数据集 business_time 仅保留为快照时间，不自动作为当前时间。
- 全部业务行 is_mock=true、source_label 以 DEMO: 开头，输出包含 DEMO 标识和真实计算证据。

## 2. 数据库与实际灌数

执行命令（项目根目录）：

```powershell
uv --cache-dir .uv-cache run --locked python scripts/seed_demo.py
```

首次执行 action=created，数据集 DEMO-v2，schema-v1，行数：

| 表 | 实际行数 | 关系 / 关键内容 |
| --- | ---: | --- |
| components | 6 | 制造商+完整料号唯一；含固定模拟参考价 |
| suppliers | 12 | DEMO 虚构名称、类型与状态 |
| offers | 18 | 关联 supplier 与 component；整数分、库存、MOQ、包装倍数、交期、有效期 |
| supplier_certifications | 11 | 关联 supplier；模拟证书状态、核验时间、生效与到期日 |
| performance_records | 66 | supplier+component+完整自然月；质检、交付、响应分子/分母 |
| demo_metadata | 1 | 数据版本、schema 版本、快照与生成时间、DEMO 声明 |

再次实际执行同一命令：action=unchanged，六表行数不变；
snapshot_time 仍为 `2026-10-21T08:20:53.174039+00:00`，没有把旧报价刷新为“刚更新”。
测试另用 tmp_path 下的独立数据库，不修改该项目 DEMO 库。

## 3. 评分与可解释性

硬筛检查精确料号/制造商、供货状态、数据完整性/时效、库存、MOQ、包装倍数、交期、
单价上限、总货款预算及证书。失败报价保留 supplier_id、offer_id、错误码、实际值和预期值。
同种错误的摘要按报价去重计数，单条报价的多张异常证书不会重复增加该原因的报价数。

合格报价采用固定锚点：价格对目录参考价；交期0–30日；合格率95%–100%；
准时率80%–100%；平均响应1–48小时。使用 Decimal、六位小数和 ROUND_HALF_UP。
历史按本型号最近六个完整月聚合分子/分母；缺失记0，小样本封顶50，不重分配缺失指标权重。

每条结果包含原值、分项分、权重、贡献、总分、报价、交期、记录级证据和风险。
同家供应商取最佳报价后再取 Top 3。同分按质量分、交期、总货款、supplier_id、offer_id 排序。
完整公式、阈值和预设权重见 scoring_design.md；这些是假设规则，不是市场最优或统计概率。

## 4. 实际 pytest 与静态检查

最终执行的命令：

```powershell
uv --cache-dir .uv-cache run --locked pytest -q
uv --cache-dir .uv-cache run --locked ruff check src scripts tests
uv --cache-dir .uv-cache run --locked ruff format --check src scripts tests
uv --cache-dir .uv-cache lock --check
```

最终实际输出摘要：

```text
........................................................................ [ 66%]
.....................................                                    [100%]
109 passed in 1.96s
All checks passed!
38 files already formatted
Resolved 85 packages in 1ms
```

各命令最终退出码均为0。覆盖正常匹配、单价/总预算独立边界、MOQ、包装倍数、库存、
完整料号与厂家身份、证书缺失/未核验/到期/撤销/未来核验、报价过期/陈旧/未来时间、
零历史、小样本、历史加权分母、缺参考价、同分排序、同家去重、候选稳定性、
证据引用与贡献契约、幂等、版本冲突、外键/CHECK、业务时钟及结构化 API。

执行过程记录：首轮99个用例通过；增加排除统计和契约防篡改测试后，一次运行出现
`1 failed, 108 passed in 2.06s`，原因是新增测试漏导入 timedelta；补充导入后得到上述最终结果。
开发中 Ruff 曾发现长行/未使用导入，已修正；最终检查通过。
本阶段未调用 DeepSeek，无付费模型测试，没有图/前端测试，也不据此宣称全系统验收通过。

## 5. 三个实际 DEMO 场景

执行：

```powershell
uv --cache-dir .uv-cache run --locked python scripts/demo_match.py
```

最终执行退出码0，clock_mode=business。
business_time=`2026-10-21T09:30:22.586686+00:00`（上海17:30:22），
dataset_snapshot_time=`2026-10-21T08:20:53.174039+00:00`。
这两个时间来自本次实际响应，不是为保证通过而回拨的日期。

共同需求：TI / LM358DR，1000 pcs，7自然日内到货，必需模拟 ISO9001。
检索13条该型号报价，4条报价通过，涉及3家不同供应商；供应商02有两条合格报价，仅占一个名额。

| 场景 / 偏好 | 第1名 | 第2名 | 第3名 | 实际状态 |
| --- | --- | --- | --- | --- |
| 正常 / balanced | DEMO 02：83.500000 | DEMO 03：80.226950 | DEMO 01：60.680851 | success |
| 成本优先 / cost | DEMO 01：73.180851 | DEMO 03：70.893617 | DEMO 02：67.000000 | success |
| 质量优先 / quality | DEMO 02：84.500000 | DEMO 03：78.893617 | DEMO 01：54.680851 | success |
| 严格单价上限1分/片 | 空 | 空 | 空 | no_match |

成本优先的第一名 DEMO 01 单价50分；质量优先第一名 DEMO 02 单价120分，
模拟质检合格率100%。DEMO 03 单价100分。变化来自权重和真实计算的分项，不是模型改写排名。
上述价格全为虚构构造数据，不代表相应料号市场价。

严格预算场景实际排除摘要：

```text
UNIT_PRICE_OVER_LIMIT: 13
INSUFFICIENT_STOCK: 1
MOQ_NOT_MET: 1
ORDER_MULTIPLE_MISMATCH: 1
CERT_UNVERIFIED: 1
CERT_VERIFICATION_MISSING: 1
CERT_EXPIRED: 1
CERT_MISSING: 1
OFFER_STALE: 1
OFFER_EXPIRED: 1
SUPPLIER_INACTIVE: 1
```

一条报价可有多个原因，计数之和不等于报价总数。系统返回空排名，没有放宽预算或推荐替代型号。

## 6. 新增与修改文件

新增业务文件：

- core/clock.py、core/identity.py。
- models/base.py、models/catalog.py。
- db/session.py、db/repositories.py、db/seed.py。
- schemas/requirement.py、schemas/result.py、schemas/snapshot.py。
- scoring/constraints.py、scoring/weights.py、scoring/engine.py。
- services/matching.py、api/routes.py。
- scripts/seed_demo.py、scripts/demo_match.py。

新增测试：tests/conftest.py、unit/test_contracts.py、unit/test_constraints.py、
unit/test_scoring.py、integration/test_database.py、integration/test_matching.py、integration/test_api.py。

修改：api/main.py；已实现包的 __init__.py；README；五份设计文档；data、scripts、tests 的 README。
本记录为新增文档。pyproject.toml、uv.lock 无新增依赖；agent、llm、frontend 仍保留占位。
数据库为被忽略的本地生成物，未建立 Git 仓库或创建提交。

## 7. 遗留问题与本阶段停止点

1. 权重、锚点和时效阈值尚未用真实采购数据标定。缺历史供应商会被保守压低，需未来人工评审策略。
2. 证书仅实现模拟状态与日期检查，不能证明元器件正品、原厂授权或真实认证有效性。
3. 当前只接受结构化单型号需求，预算不含运费；无替代料、拆单、阶梯价、库存锁定或真实供应商接入。
4. DEMO 库按实际时间自然过期；重复初始化不会隐藏过期。需要新数据时选新的专用文件。
5. 当前六表强制 DEMO 数据；若将来接真实企业数据，需单独审核数据来源与模式，不能直接解除标识后声称可信。
6. SQLite 数据表迁移、持久化请求审计、多进程并发、权限与生产运维未实现。
7. 自然语言、DeepSeek、LangGraph 和 Streamlit 尚未开始；等待审核后再进入下一阶段。
