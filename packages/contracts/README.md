# ComponentMatch HTTP 契约

`componentmatch-contracts` 是前后端共享的独立包，只依赖 Pydantic，不导入后端、数据库、模型 SDK 或 Streamlit。

- `requirement.py`：采购需求、金额边界和结构化接口输入。
- `result.py`：评分、证据、风险和确定性匹配响应的不变式。
- `agent.py`：自然语言请求、显式确认、澄清字段、模型调用记录和 Agent 响应。

数据库内部快照保留在后端 `componentmatch/schemas/snapshot.py`，不属于公共 HTTP 契约。修改公共契约时需要同时验证两端。工作区通过一个 `uv.lock` 保持接口包版本一致；若将来分仓或独立发布，需要发布该包并固定兼容版本。
