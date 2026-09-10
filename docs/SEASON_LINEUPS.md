# DeepSeek 赛季最佳阵容

## 评选口径

- 最佳一阵与二阵各 5 人，两个阵容的 10 名选手不得重复。
- 每阵固定 1 名主狙和 4 名步枪手，并覆盖突破、支援与残局功能；系统不根据统计猜测 IGL。
- 候选人至少出场 3 场，且出场数达到该赛季最高出场数的 50%。
- DeepSeek 完成 21 轮独立评审，个人影响与团队成绩各占 50%。代码验证每张选票并在阵容约束下聚合；少于 15 张有效票或任一评审视角少于 4 张票时不发布。
- 高级指标的缺失值不会转换成 0，Demo 指标始终携带覆盖场次。

进行中赛季只从后台“荣誉奖项”页面手动触发。赛季归档时，如果最新成功结果仍对应当前数据，系统直接封存；否则自动排队生成最终版。

## 部署

评选任务复用 `player-summary-worker` 容器，但在独立的 `season-lineup` 队列中执行。除现有 DeepSeek 和 Redis 配置外，可设置：

```dotenv
SEASON_LINEUP_PROMPT_VERSION=v1
SEASON_LINEUP_BALLOTS=21
```

修改 prompt、角色计算或输出约束后应递增 `SEASON_LINEUP_PROMPT_VERSION`。同一数据哈希、模型和 prompt 版本的成功结果不会重复调用 API。

## 状态与公开数据

运行状态包括 `pending`、`queued`、`generating`、`completed`、`failed`、`superseded`、`insufficient_data` 和 `blocked_configuration`。

公开荣誉接口的 `all_star_lineups` 只返回阵容、角色、证据、入选率、覆盖率和数据时间，不返回原始 prompt、完整票仓或内部错误。后台保留最近 10 次运行摘要；数据库保存完整输入快照与有效票，便于复核。
