# union-davinci-task

本项目是达芬奇做图工单后台 worker。

- 中文沟通、中文注释、中文日志。
- 不复制 `union-agent` 的达芬奇做图逻辑；通过导入并调用 `union-agent` 现有编译、出图、任务状态函数来保持逻辑一致。
- 数据库写入仅限 `union_davinci_draworder` 工单状态与结果字段。
- 默认每 5 分钟轮询一次，也支持 `--once` 单次执行。

