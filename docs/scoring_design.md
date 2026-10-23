# 硬约束与确定性评分设计

版本：已实现规则 `score-v0.2`。阈值、参考价与权重均为 DEMO 假设，非已标定的行业标准。
第二阶段默认权重以本轮用户要求为准：质量30%、价格20%、交期25%、历史交付20%、响应5%。
排名来自 Python Decimal 计算，无大模型调用。

## 1. 计算对象与执行顺序

结构化需求校验 → 精确组件身份 → 报价数据有效性 → 硬约束 → 分项归一化 →
加权总分 → 每家供应商取最佳一条报价 → 固定排序 → Top 3 → 证据与解释。

排序的是“本次需求对应的供应商报价”，不计算跨型号的永久供应商等级。
硬约束没有分数，不通过就退出；不能靠低价抵消型号、数量、交期或证书不符合。

## 2. 硬约束清单

| 检查 | 通过规则 | 数据来源 / 失败代码 |
| --- | --- | --- |
| 型号身份 | manufacturer_key、完整 part_number_key 等于已解析目录身份 | components；COMPONENT_MISMATCH |
| 供货状态 | supplier.status=active 且 offer.status=active | suppliers/offers；SUPPLIER_INACTIVE / OFFER_INACTIVE |
| 数据已知且有效 | 价格>0、库存>=0、交期>=0、MOQ/倍数>0，币种为 CNY | offers；OFFER_DATA_MISSING / OFFER_DATA_INVALID |
| 数据时效 | observed_at ≤ business_time ≤ valid_until，且快照年龄 ≤7×24 小时 | offers；OFFER_EXPIRED / OFFER_STALE / FUTURE_DATA |
| 数量足量 | available_quantity ≥ quantity | offers + 需求；INSUFFICIENT_STOCK |
| 可以准确下单 | quantity ≥ MOQ 且 quantity % order_multiple=0 | offers；MOQ_NOT_MET / ORDER_MULTIPLE_MISMATCH |
| 到货时间 | 有硬上限时 lead_time_days ≤ max_delivery_days | offers + 需求；DELIVERY_TOO_SLOW |
| 单价上限 | unit_price_cents ≤ max_unit_price_cents（若设置） | UNIT_PRICE_OVER_LIMIT |
| 总货款预算 | unit_price_cents×quantity ≤ total_budget_cents（若设置），可与单价上限并存 | TOTAL_BUDGET_EXCEEDED |
| 必需证书 | 每个必需代码至少一张模拟 verified 且在业务日期有效、核验不在未来的证书 | CERT_MISSING / CERT_UNVERIFIED / CERT_EXPIRED / CERT_REVOKED / CERT_NOT_YET_VALID / CERT_VERIFICATION_MISSING / CERT_VERIFICATION_FUTURE |

“库存足量”与“可在交期内到货”是种子报价的联合承诺定义，不再推断未来补货。
exact match 查询通常不会返回不同型号，但硬筛仍校验 component_id 防御数据关联错误。
所有边界包含等号；证书到期日当天有效，报价 valid_until 时刻有效；时钟来源见数据库设计。
7 日阈值是待确认的演示数据策略；不能说是电子元器件行业统一库存有效期。

无匹配时返回逐报价全部失败代码及统计，并提供“可人工检查预算或交期”等一般提示。
不自动重跑放宽后的需求，也不展示未通过型号约束的“备选推荐”。

## 3. 评分指标、固定归一化与数据来源

记 `clip(x)=min(1,max(0,x))`，每个分项范围为 [0,100]。使用固定锚点，
不根据本次候选最大/最小值归一化，避免增加一个离群候选导致其他人的分数漂移。
参考价和时效均使用同一业务时钟和版本配置。

| 指标 | 公式（未应用样本保护前） | 原值与证据来源 |
| --- | --- | --- |
| 价格 P | `100 × clip((1.5×r-p)/r)` | p=offers.unit_price_cents；r=components.reference_unit_price_cents |
| 交期 D | `100 × clip((30-d)/30)` | d=offers.lead_time_days，单位自然日 |
| 质量 Q | `100 × clip((a/n-0.95)/0.05)` | a=Σaccepted_units，n=Σinspected_units |
| 准时交付 O | `100 × clip((o/t-0.80)/0.20)` | o=Σorders_on_time，t=Σorders_due |
| 响应服务 R | `100 × clip((48-h)/47)` | h=Σresponse_minutes_total / Σresponse_samples / 60 |

锚点解释：

- 价格为参考价的 0.5 倍及以下得 100，等于参考价得 50，1.5 倍及以上得 0。
  低价额外风险见下文；不将低价视为正品证明。
- 0 天交期得 100，30 天及以上得 0。若硬上限放宽到 45 天，则 35 天可通过但交期分为 0。
- 合格率 95% 及以下得 0，100% 得 100；95% 是归一化下锚点，不是本版硬性淘汰线。
- 准时交付率 80% 及以下得 0，100% 得 100，逾期未完成订单仍在分母中。
- 平均响应 1 小时及以内得 100，48 小时及以上得 0；无样本不按 0 分钟计算。

参考价来自人为设计的模拟目录，不能引用成市场均价。参考价为空、<=0、未来时间，
或年龄超过 30×24 小时时，价格分为 0，标记 PRICE_REFERENCE_UNAVAILABLE，
仍可按报价执行预算硬筛。其权重保持不变，不转给其他维度。

Q、O、R 仅聚合本供应商本型号最近六个完整自然月的有效记录，
窗口定义见数据库设计。无效行剔除并标记 HISTORY_ROW_INVALID；不使用其他型号填补。
记录覆盖不足六个月标记 HISTORY_PARTIAL_WINDOW；不把缺失月份当作优秀表现。
若没有有效记录或最近记录的 period_end 距 business_date 超过 62 日，
Q/O/R 全部为 0，标记 HISTORY_MISSING / HISTORY_STALE。

## 4. 小样本与缺失保护

不把未知填成满分，不对每个候选重新归一化权重，否则缺数据者可能获得不公平优势。

| 情况 | 保守处理 |
| --- | --- |
| n=0（无质检件数） | Q=0；QUALITY_HISTORY_MISSING |
| n>0 且 (n<500 或 Σquality_evaluated_orders<5) | Q=min(原始Q,50)；QUALITY_SAMPLE_SMALL |
| t=0（无应交订单） | O=0；DELIVERY_HISTORY_MISSING |
| 0<t<5 | O=min(原始O,50)；DELIVERY_SAMPLE_SMALL |
| 响应样本数=0 | R=0；RESPONSE_HISTORY_MISSING |
| 0<响应样本数<5 | R=min(原始R,50)；RESPONSE_SAMPLE_SMALL |

历史缺失不默认硬淘汰，便于展示冷启动；但它会失去对应权重得分并带风险提示。
此规则可能压低新供应商，需要在真实业务中由采购人员决定是否进入人工评审池，
本版不宣称该规则已解决冷启动公平性。没有统计置信度模型，也不输出“成功概率”。

## 5. 可配置权重与总分

| profile | P 价格 | D 交期 | Q 质量 | O 准时交付 | R 响应 | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| balanced（默认） | 0.20 | 0.25 | 0.30 | 0.20 | 0.05 | 1.00 |
| cost | 0.45 | 0.15 | 0.20 | 0.15 | 0.05 | 1.00 |
| delivery | 0.20 | 0.40 | 0.20 | 0.15 | 0.05 | 1.00 |
| quality | 0.20 | 0.15 | 0.40 | 0.20 | 0.05 | 1.00 |

`total = wP×P + wD×D + wQ×Q + wO×O + wR×R`，范围 [0,100]。
权重已放入 scoring/weights.py 并附 rule_version；用户仅选择命名档位，
不允许模型自由输出五个权重。开发配置可调整，必须校验键齐全、有限非负且 Decimal 和精确为 1。
非法配置报错，不自动重标定；每次响应保存所用配置。

使用 Decimal；分项和加权贡献 ROUND_HALF_UP 到六位小数，内部总分为五个六位贡献之和。
按内部总分排序，界面分项/总分通常显示两位小数，并允许展开六位贡献。
展示两位小数时可能有 0.01 左右加总差异，说明显示舍入，不用显示值反向排序。

固定排序键：内部总分降序 → Q 分降序 → lead_time_days 升序 →
总货款分升序 → supplier_id 升序 → offer_id 升序。
先按该键为每家选一条报价，再从不同供应商中取前三名。结果不足三个时不补充不合格者。

## 6. 风险规则与解释边界

| 风险 | 规则 / 来源 | 是否额外扣分 |
| --- | --- | --- |
| LOW_PRICE_REVIEW | 有效参考价且 p<0.5r；模拟报价低于锚点 | 不额外扣分，提示人工复核 |
| STOCK_TIGHT | quantity>0 且 available_quantity/quantity<1.2 | 不额外扣分，提示库存余量小 |
| NO_DELIVERY_BUFFER | 有交期上限且 d=max_delivery_days | 不额外扣分，提示交期无余量 |
| CERT_EXPIRING_SOON | 被用于满足必需资质的有效证书在 30 自然日内到期 | 不额外扣分，展示证据 |
| HISTORY_*、*_SAMPLE_SMALL | 历史时效、覆盖、分母或样本不足 | 已通过分项保守处理，禁止再扣一次 |
| PRICE_REFERENCE_UNAVAILABLE | 缺失/失效参考价 | 已将价格分置 0，禁止双重惩罚 |
| MOCK_DATA_ONLY | 所有记录均为模拟 | 永远展示，不作为数值扣分 |

风险不是正品鉴定、法律合规结论或违约概率。必须展示的风险由 Python 生成，
不能被 LLM 隐藏；LLM 只组织理由引用和顺序，原值/分数/排名由后端固定。
解释只能说“在本次模拟数据和规则下排名靠前”，不得说“已核实真实库存充足”或“保证正品”。

## 7. 可手算的规则示例（不是系统运行结果）

仅为核对公式，假设某条已通过硬筛的模拟报价：p=r，则 P=50；d=6，则 D=80；
六个月有效样本充足且 a/n=0.99，则 Q=80；o/t=0.96，则 O=80；h=1，则 R=100。
balanced 总分：`0.20×50 + 0.25×80 + 0.30×80 + 0.20×80 + 0.05×100 = 75`。
独立手算期望已用于 pytest 校验；该例不是某家供应商的实际采购结果。

## 8. 持续回归验证重点

- 同一快照/规则/结构化需求重复计算，数值、风险和排名一致；LLM 措辞不在确定性承诺内。
- 价格或交期单独改善且其他输入固定时，相应分项和总分不下降。
- 加入劣质候选不会改变已有候选的分数；同一家多条报价不重复占位。
- 预算/库存/证书/时效边界、零分母、样本阈值前后、缺失参考价、同分和舍入均有测试。
- 分数不是概率；权重敏感性可用不同 profile 对比，不能把更改权重包装成模型智能发现。
