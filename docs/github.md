# 上传到 GitHub

本项目已经包含忽略规则、空密钥配置模板、CI、换行规范和贡献模板。下面的命令由项目拥有者在本地执行；仓库地址取决于你创建的 GitHub 仓库。

## 1. 创建空仓库

在 GitHub 创建仓库并自行选择 Public 或 Private。不要勾选自动创建 README、`.gitignore` 或许可证，避免与本地项目的首次提交冲突。复制仓库的 HTTPS 地址。

如果电脑尚未安装 Git，可从 [Git for Windows 官方页面](https://git-scm.com/download/win) 下载；安装后重新打开终端，确认 `git --version` 能正常运行。已有本地 `.git` 时不必再次初始化；没有时执行 `git init -b main`。

## 2. 本地检查

进入项目根目录，按 [贡献说明](../CONTRIBUTING.md) 运行检查。然后查看：

```powershell
git status --short
git check-ignore .env .venv-backend .venv-frontend .venv-dev data/componentmatch.db logs
```

源码、`uv.lock`、`.env.example`、文档和公开截图应提交；真实 `.env`、虚拟环境、SQLite 文件、缓存和运行日志不提交。若某个本地文件尚不存在，`git check-ignore` 的输出可能不列出它。

## 3. 创建第一次提交

```powershell
git add .
git diff --cached --stat
git diff --cached --name-only
```

核对暂存文件，确认没有凭据或本机数据后，再执行：

```powershell
git commit -m "Initial commit: ComponentMatch Agent"
```

如果 Git 提示缺少作者信息，可按提示设置本仓库的 `user.name` 和 `user.email`，然后重试提交。

## 4. 关联地址并推送

先查看现有远程配置：

```powershell
git remote -v
```

若尚无 `origin`，执行下面的命令，并在提示时粘贴刚创建的仓库地址：

```powershell
$repositoryUrl = Read-Host '粘贴 GitHub 仓库 HTTPS 地址'
git remote add origin $repositoryUrl
git push -u origin main
```

按 Git 的提示完成 GitHub 身份验证。已有 `origin` 时先核对地址，不重复添加，也不要为了处理冲突强制推送。

上传后打开仓库的 **Actions** 页面查看第一次 CI。成功前不要把仓库描述或 README 标为远端 CI 已通过。当前工作流不需要添加 DeepSeek Secrets。

以上流程依据 [GitHub 官方本地项目上传说明](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)。

## 5. 在另一台电脑获取

先安装 Git，选择一个父目录，再执行：

```powershell
$repositoryUrl = Read-Host '粘贴 GitHub 仓库 HTTPS 地址'
git clone $repositoryUrl componentmatch-agent
Set-Location componentmatch-agent
```

然后按 [README 的首次启动步骤](../README.md) 安装 uv、重建环境、配置自己的密钥并初始化数据。虚拟环境和用户配置不会随仓库克隆。
