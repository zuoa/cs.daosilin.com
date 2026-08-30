# 对外选手数据 API

## 配置

登录「管理后台 → API 与安全」即可生成、保存或撤销 token。系统生成的 token 只在生成当次显示明文，数据库仅保存单向密码哈希和末 4 位提示。

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

每个选手都包含 `player_id`、昵称、头像、别名、Steam ID、直播地址，以及完整统计字段。其中必定包含：

- `avg_adpr`
- `avg_rating`
- `fk_fd_ratio`
- `avg_kast` / `kast_ratio`
- `avg_headshot_ratio`

`avg_adpr` 使用“总生命伤害 / 总回合”，`avg_kast` 使用“KAST 回合数 / 总回合”，`avg_headshot_ratio` 使用“总爆头 / 总击杀”；它们都是跨场次加权口径，不是逐场百分比的算术平均。

可直接使用的扩展指标包括：

- 回合效率：`total_rounds`、`kills_per_round`、`deaths_per_round`、`assists_per_round`。
- 开局对枪：`opening_duel_win_rate`、`opening_duels_per_round`。
- 多杀与 MVP：`multi_kill_rounds`、`multi_kill_round_rate`、`mvp_match_rate`。
- 闪光：`total_flash_success`（敌方致盲事件）、`total_flash_teammate`（队友致盲事件）、`enemy_flashes_per_round`、`team_flashes_per_round`、`team_flash_share`。
- 团队与道具：`total_trade_frags`、`trade_kill_share`、`total_grenade_damage`、`total_inferno_damage`、`total_utility_damage`、`utility_damage_per_round`、`throws_per_round`。
- 对位击杀：`kill_matchups`，按对手聚合并按击杀次数降序排列。

所有比率字段为 `0.0-1.0`，例如 `win_rate: 0.625` 表示 62.5%。WMPVP 当前的 `flash`（闪光投掷数）始终为 0，无法作为成功率分母，因此兼容字段 `flash_success_ratio` 与 `flash_teammate_ratio` 固定返回 `0.0`，新接入方不应使用它们。

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
