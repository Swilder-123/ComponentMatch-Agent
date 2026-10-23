# DEMO 数据准备

本目录保存本机 SQLite 文件。全部数据为虚构 DEMO，不代表任何真实企业的库存、价格、资质或评价。数据库已被 Git 忽略；拷贝到新电脑时可以不带数据库，按下面的步骤重新生成。

## 第一次准备

从仓库根目录执行，先完成 `scripts/setup.ps1 -Target Backend`：

```powershell
.\.venv-backend\Scripts\python.exe scripts/seed_demo.py
```

脚本读取根目录 `.env` 的 `DATABASE_URL`；默认是 `sqlite:///./data/componentmatch.db`。`--database-url` 参数优先级最高。它会创建缺失的目录和六张表，写入 6 个元器件、12 家 DEMO 供应商、18 条报价、11 张证书、66 条月度绩效以及一条元信息记录。

已有同版本、记录数完整的库返回 `unchanged`，不重复插入，不刷新时间；版本不一致或数据不完整时明确失败。启动服务不会自动建库或灌数。

## 旧电脑复制来的数据过期了

业务使用实际时间。报价快照超过7天或超过有效期，就不会参与推荐。**重复执行 seed 不会续期旧数据，也不要修改电脑时间或直接改时间戳。**

请给新演示选择一个尚未存在的文件名，例如：

```powershell
.\.venv-backend\Scripts\python.exe scripts/seed_demo.py --database-url sqlite:///./data/demo-new.db
notepad .env
```

把 `.env` 中的配置改为：

```dotenv
DATABASE_URL=sqlite:///./data/demo-new.db
```

然后重启后端。一键启动会输出活跃报价数、时效合格报价数、过期/陈旧报价数和过期核验资质数。统计用于提醒，实际候选仍须经过库存、MOQ、包装倍数、交期、预算和资质等全部硬筛。

原数据库保留，不会被新库覆盖。下次需要新数据时再次换一个文件名。

## 验证数据和规则（不调用模型）

```powershell
.\.venv-backend\Scripts\python.exe scripts/demo_match.py
# 或明确选择新库：
.\.venv-backend\Scripts\python.exe scripts/demo_match.py --database-url sqlite:///./data/demo-new.db
```

所有业务表必须 `is_mock=true`、来源以 `DEMO:` 开头，证书编号以 `MOCK-` 开头。种子源码在 `backend/src/componentmatch/db/seed.py`；测试使用临时数据库和固定时钟，不读取或刷新这里的文件。
