# 开发与贡献

先阅读 [README](README.md) 和 [架构说明](docs/architecture.md)。本项目是使用虚构数据的本机采购匹配 Demo。

## 本地开发

从仓库根目录执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Target Dev
.\.venv-dev\Scripts\python.exe -m pytest -q
.\.venv-dev\Scripts\ruff.exe check backend frontend packages scripts tests
.\.venv-dev\Scripts\ruff.exe format --check backend frontend packages scripts tests
.\.venv-dev\Scripts\python.exe scripts/check_docs.py
uv --cache-dir .uv-cache lock --check
```

依赖变化时更新对应包的 `pyproject.toml` 和根 `uv.lock`。前端只通过 HTTP 访问后端；公共契约不得依赖业务实现。新增行为应覆盖有意义的边界，不要通过调整评分权重、种子日期或测试时钟掩盖问题。

## 提交与 PR

使用描述修改内容的分支名，保持提交范围集中。PR 说明应包含问题、最终行为、验证结果和已知限制。接口或启动方式变化时同步当前文档；历史报告位于 `docs/history/`，保留原日期与测试结论。

默认测试使用 Mock 和临时数据库，不需要 API Key。不要提交 `.env`、数据库、虚拟环境或运行日志；截图需注明 DEMO / Mock 来源。真实模型检查是单独的手动流程，不加入默认测试和 CI。

`.gitattributes` 管理 Git 换行符，`.editorconfig` 管理编辑器默认格式。Python 以 Ruff 结果为准。提交前检查 `git diff --cached`，确认没有机器路径或凭据。

## 问题反馈

Issue 中说明环境、复现步骤、预期与实际行为，附脱敏后的错误码和请求 ID。功能建议应明确使用场景、输入输出及验收方式。完整发布步骤见 [GitHub 上传指南](docs/github.md)。
