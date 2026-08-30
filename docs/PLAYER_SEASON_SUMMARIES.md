# DeepSeek 选手赛季点评

## 部署

在部署环境中配置：

```dotenv
LLM_API_KEY=your-deepseek-api-key
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL_NAME=deepseek-v4-flash
LLM_REQUEST_TIMEOUT=45
PLAYER_SUMMARY_PROMPT_VERSION=v1
```

`docker compose` 会启动独立的 `player-summary-worker`，只消费
`player-summary` 队列。API Key 不写入数据库，也不会由管理接口返回。

## 生成规则

- 每轮赛季采集完成后按输入哈希增量生成；调度器每 10 分钟补齐历史和遗漏任务。
- 比赛数、胜负、回合和 K/D/A 等逐场必有字段可以保留真实零值。
- 无法区分“真实为零”与“上游缺失补零”的高级字段，在值为零时不会进入提示词。
- 比率仅在分母有效时生成；Demo 指标会携带实际覆盖场次。
- 修改提示词后递增 `PLAYER_SUMMARY_PROMPT_VERSION`，系统会自动重新生成。

后台“API 与安全”页面可以查看状态，并重算单个选手或整个赛季。公开详情接口在
`season_summary` 字段返回最后一版成功结果；刷新失败时仍保留旧结果，内部错误仅后台可见。
