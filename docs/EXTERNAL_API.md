# 对外选手数据 API

## 配置

登录「管理后台 → API 与安全」即可生成、保存或撤销 token。系统生成的 token 只在生成当次显示明文，数据库仅保存单向密码哈希和末 4 位提示。

同一页面提供“在线测试”：输入 token，选择列表或个人接口及查询参数后，可直接查看 HTTP 状态、耗时与完整 JSON 响应。刚生成或保存的 token 会自动填入测试器，刷新页面后不会保留。

也可在生产环境设置 `EXTERNAL_API_TOKEN` 后重启应用。环境变量优先级高于后台保存的 token，此时后台将它显示为只读配置。两种方式都没有配置时，对外接口返回 HTTP 503，不会匿名开放。

```bash
openssl rand -hex 32
```

## 调用

接口：`GET /api/v1/external/players`

token 建议通过 Bearer header 传递，不要放在 URL 中：

```bash
curl -H 'Authorization: Bearer YOUR_TOKEN' \
  'https://cs.daosilin.com/api/v1/external/players?season=all'
```

`X-API-Token: YOUR_TOKEN` 也可以使用。

`season` 参数支持：

- `all`：合并统计全部已配置赛季。
- `last`：统计结束时间最新的已结束/已归档赛季；不传参数时默认为 `last`。
- 赛季名称：可传 `cup_name`、赛季别名或展示名。

也可以把选择器直接放在路径中，例如：

```text
GET /api/v1/external/players/all
GET /api/v1/external/players/last
GET /api/v1/external/players/<URL 编码后的赛季名>
```

## 返回数据

`data.seasons` 说明本次统计实际命中的赛季，`data.player_count` 是选手数，`data.players` 是每个选手的合并统计。

External API 只提供选手身份、基础比赛数据、当前完美平台段位和 AI 球探报告。站内 Demo 分析、高级指标、对位榜等数据不会通过此接口返回。

选手身份字段包括 `player_id`、`nickname`、`avatar`、`alias_name`、`steam_id`、`live_url` 和 `live_room_id`。

基础比赛数据包括：

- 场次与胜负：`match_count`、`win_count`、`win_rate`、`total_rounds`。
- 击杀数据：`total_kills`、`total_deaths`、`total_assists`、`kd_ratio`、`total_first_kills`、`total_first_deaths`、`total_headshots`、`avg_headshot_ratio`、`total_mvp`。
- 平均表现：`avg_rating`、`avg_pw_rating`、`avg_adpr`、`avg_kast`。

每个选手还会返回当前完美平台段位与按赛季生成的个人球探报告：

- `perfect_rank.score`：当前天梯分，尚未采集时为 `null`。
- `perfect_rank.level`：当前段位，例如 `B`、`A`、`S21`，尚未定级或未采集时为 `null`。
- `perfect_rank.updated_at`：最近一次成功采集段位的 ISO 8601 时间。
- `scouting_reports`：本次命中赛季中已经建立的球探报告列表。每项包含 `cup_name`、`season_name` 和 `report`；报告生成中时 `report.status` 为 `pending`，完成后会包含 `headline`、`overview`、`strength`、`weakness`、`style`、`sample`、`generated_at`、`refreshing` 与 `stale`。

球探报告始终保持单赛季口径。`season=all` 返回的比赛统计是跨赛季合并值，但 `scouting_reports` 不会把多赛季报告合并；尚未建立报告任务的赛季不会出现在列表中。

`avg_adpr` 使用“总生命伤害 / 总回合”，`avg_kast` 使用“KAST 回合数 / 总回合”，`avg_headshot_ratio` 使用“总爆头 / 总击杀”；它们都是跨场次加权口径，不是逐场百分比的算术平均。所有比率字段为 `0.0-1.0`，例如 `win_rate: 0.625` 表示 62.5%。

## 查询单个选手

接口：`GET /api/v1/external/player`

必须且只能提供以下一个查询参数：

- `steam_id`：Steam ID；兼容别名 `steamid` 和 `STEAMID`。历史数据中 Steam64 ID 存在 `player_id` 时也可以命中。
- `room_id`：由“直播平台 + `_` + 房间号”组成，例如 `DOUYU_9999`；兼容参数别名 `roomid` 和 `room`，查询值大小写不敏感。系统根据后台为选手配置的直播间 URL 生成该值，当前可识别 `DOUYU`、`HUYA`、`BILIBILI`、`DOUYIN`、`KUAISHOU`、`CC`、`YY` 和 `TWITCH`。

个人接口使用相同的 token，并支持相同的 `season` 选择规则：

```bash
curl -H 'Authorization: Bearer YOUR_TOKEN' \
  'https://cs.daosilin.com/api/v1/external/player?steam_id=76561198000000000&season=all'

curl -H 'Authorization: Bearer YOUR_TOKEN' \
  'https://cs.daosilin.com/api/v1/external/player?room_id=DOUYU_9999&season=last'
```

成功时 `data.player` 返回该选手在所选赛季的合并统计，字段与选手列表中的单项一致；`data.lookup` 说明实际使用的查询类型和值。如果选手不存在，或该选手在所选赛季没有比赛数据，接口返回 HTTP 404。
