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

其他统计包括场次/胜率、K/D、击杀/死亡/助攻、首杀/首死、爆头、多杀、1vN、闪光、命中、投掷物、MVP、RWS、KAST、WE 等聚合字段。比率为 `0.0-1.0`，例如 `win_rate: 0.625` 表示 62.5%。

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
