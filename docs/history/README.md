# 历史报告

这些文件记录各阶段当时的检查结果，保留原日期、测试数量、成功/失败和限制。本次只调整归档位置、文档引用及机器路径匿名化，不改写历史验收结果。

**当前安装与使用请阅读 [主 README](../../README.md)，当前验证范围见 [验证索引](../verification.md)。** 历史报告中的目录、环境名称和命令可能已失效；其中提到的本地 `logs/` 证据不随 Git 仓库上传。

| 报告 | 内容 |
| --- | --- |
| [第二阶段验证](phase2_verification.md) | 数据库、确定性评分和结构化 API |
| [第三阶段审查](phase3_audit.md) | 早期审查问题与复现范围 |
| [第三阶段最终验证](phase3_final_verification.md) | 后端问题修复与离线回归 |
| [真实模型准备](deepseek_live_preparation.md) | 当时的配置和执行边界 |
| [真实模型联调](deepseek_live_verification.md) | 历史指定场景的实际 DeepSeek 调用 |
| [第四阶段验证](phase4_verification.md) | 中文工作台、启动与交互 |
| [第五阶段历史验收](final_acceptance.md) | 早期双入口页面验收 |
| [AI 单入口验证](ai_only_verification.md) | 页面统一为 Agent 入口 |
| [前后端分离验证](refactor_verification.md) | 独立环境、403项回归与源码迁移启动 |

历史模型联调成功不保证当前网络、账户或模型可用。默认 CI 使用离线替身，不重新执行真实模型调用。
