# union-davinci-task

达芬奇做图工单队列 worker。

## 功能

- 每隔 5 分钟扫描 `union_davinci_draworder`。
- 原子认领 `待做图` 工单，状态改为 `做图中`。
- 复用 `union-agent` 现有达芬奇逻辑完成：
  - `compile_plan`
  - `compile_plan_reflow`
  - `compile_plan_override`
  - `generate`
- 做图完成后，把图片 URL 写回 `union_davinci_draworder.output_urls`，状态改为 `已完成`。
- 做图失败时不新增状态，按当前表约束退回 `待做图`，并把错误写入 `config.last_error`，次数写入 `config.attempt_count`。
- 默认走国外 `wolfai/Gemini`；当国外供应商链路失败时，worker 会临时切到 `union-agent` 已有国产生图网关兜底重试一次。

## 运行

推荐直接复用 `union-agent` 的虚拟环境：

```bash
cd /Users/echo/Documents/Codex/2026-06-18/union-davinci-task
bash run.sh --once
```

常驻运行：

```bash
bash run.sh
```

自定义轮询间隔：

```bash
DAVINCI_TASK_INTERVAL_SECONDS=300 bash run.sh
```

## 数据库

worker 默认复用 `union-agent` 环境文件里的 `DATABASE_URL`，但只把数据库名切到
`union_prod`，不写死账号、密码、主机：

```bash
DAVINCI_TASK_DATABASE_NAME=union_prod bash run.sh --once
```

达芬奇相关 SQL 通过 `union-agent` 的 `get_davinci_pool()` 使用独立连接池，
默认 `search_path=davinci,public,app`。不要修改全局 `get_pool()` 的
`search_path`，否则会影响全系统其他路由。

## 路径说明

默认自动使用同级目录：

- `../union-lab-union-agent-git-https`
- `../union-lab-union-knowledgebase-git-https`

如果目录不同，用环境变量覆盖：

```bash
UNION_AGENT_PATH=/path/to/union-agent \
UNION_KNOWLEDGEBASE_PATH=/path/to/union-knowledgebase \
bash run.sh
```
