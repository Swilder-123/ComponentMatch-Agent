# 验证索引

## 已执行的本地基线

前后端分离后的基线为 **403 项 pytest 回归通过**，另有 Ruff、格式和锁文件检查通过。还实际执行了独立安装/启动、只复制源码的新目录安装，以及13项桌面/窄屏浏览器检查。详细数字和执行范围保留在 [归档报告](history/refactor_verification.md)。

默认测试使用临时 SQLite、固定测试时钟与显式 Mock，阻止默认外部 HTTP 传输。浏览器截图同样使用显式 Mock，不能当作真实 DeepSeek 调用证据。可公开查看的 [界面截图](images/README.md) 已从本地运行日志中单独选出。

## GitHub CI

配置位于 [ci.yml](../.github/workflows/ci.yml)，在 push、pull request 或手动触发时，以 Windows / Python 3.11 执行：

1. 使用 `uv.lock` 安装到独立 `.venv-ci`，不创建用户 `.env`。
2. 运行 Ruff 检查与格式检查。
3. 校验仓库内 Markdown 本地链接和个人 Windows 主目录路径。
4. 运行离线 pytest，再校验锁文件。

CI 不使用仓库模型密钥，不运行真实模型联调、手动浏览器检查或完整安装模拟。上传 GitHub 后才能查看实际远端结果；当前文件中的本地通过记录不代表远端 CI 已运行。

2026-10-23 已在新建的本地 `.venv-ci` 中逐条执行工作流的6个运行步骤，安装、Ruff、格式、文档链接、403项离线测试和锁文件检查全部通过。Actions 的检出及工具安装步骤未在 GitHub 运行；本地执行记录保存在不提交的 `logs/github-prep/`。

配置方法参考 [uv 官方 GitHub Actions 指南](https://docs.astral.sh/uv/guides/integration/github/)。

## 本地复验

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Target Dev
.\.venv-dev\Scripts\ruff.exe check backend frontend packages scripts tests
.\.venv-dev\Scripts\ruff.exe format --check backend frontend packages scripts tests
.\.venv-dev\Scripts\python.exe scripts/check_docs.py
.\.venv-dev\Scripts\python.exe -m pytest -q
uv --cache-dir .uv-cache lock --check
```

手动的源码迁移检查及浏览器检查会安装或使用额外工具，命令与前提见 [测试说明](../tests/README.md)。实际运行日志保留在本地 `logs/`，不提交到 Git。

## 历史结果

历次验证集中在 [历史索引](history/README.md)。旧记录只说明其当时的状态，当前架构与启动方式以 [README](../README.md) 为准。
