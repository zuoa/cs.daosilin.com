# 宝可梦选人终稿服务

当前阶段只做两件事：监听宝可梦选人终稿，并在独立公开页面展示。比赛拟合留到下一阶段，不进入现有比赛采集、Demo 或统计链路。

## 当前能力

- 队伍数量动态，可为 8、10 或其它数量。
- 每队人数动态，各队可以不等长。
- slot 1 是队长，slot 2 以后依次为第 1 选、第 2 选，不设固定上限。
- middleArea 可以保留替补，不参与终稿，也不影响完成。
- 分组名称动态，不写死 A-D；每个分组表示两队对阵。
- 生产只存终稿，不存原始帧、拖动过程、ready 名单或登录信息。

## 协议

连接过程与浏览器客户端一致：

1. HTTP long-poll `GET /socket.io/?EIO=4&transport=polling` 取得 Engine.IO sid。
2. 使用 sid 升级到 WebSocket。
3. `2probe` / `3probe` / `5` 完成升级。
4. 发送 `40` 连接默认 namespace。
5. 发送 `42["loading", md5(password), {"attendanceCode": password}]` 登录。
6. 服务端发送 `2...` ping 时回复 `3...`。

生产配置：

```text
BAOKEMENG_PASSWORD=...
BAOKEMENG_SERVER=https://www.baokemeng.xyz
BAOKEMENG_STABLE_SECONDS=5
```

真实事件结构：

- `loading`
  - `args[1]`：完整盘面，包含 topArea、middleArea、bottomArea。
  - `args[2]`：配置，包含 appSettings、adminToC 等。
- `updatePlayerPosition`
  - `args[0]`：JSON 字符串，包含 moved、added、removed、changed、snapshot。
  - `args[1]`：本次配置，包含 adminToC.teamBat。

每次增量都以 snapshot 覆盖内存，不模拟 moved。changed 造成的 ready 状态变化不会改变有序阵容指纹。

## 完成状态机

冷启动时可能直接看到上一轮完整阵容及旧 teamBat，因此 loading 只建立基线，不写库。

一轮终稿按以下流程确认：

1. topArea 的有序阵容发生变化，标记本轮开始。
2. 收到与基线不同的 teamBat。
3. teamBat 唯一且完整覆盖当前所有非空队伍。
4. 每个分组恰好包含两支队伍。
5. 有序阵容和 teamBat 连续稳定 `BAOKEMENG_STABLE_SECONDS` 秒。
6. 在一个数据库事务中写入 session、teams、players。

如果稳定窗口内盘面或 roll 再变化，重新计时；roll 被清空或退回本轮基线时立即撤销待提交项。如果选人开始后断线，重连 loading 会保留当前轮次，并把 loading 中的实时 roll 重新纳入判断。提交成功后清空本轮开始时间。同一终稿重连不会重复插入；同一阵容重新 roll 会生成新终稿并将旧 roll 版本标为 superseded。若 roll 出现 A→B→A，则重新启用原 A 版本并更新完成时间，同时将 B 标为 superseded。

队伍数量优先参考 `appSettings.topAreaNum`，同时以 topArea 的实际 area 集合兜底，避免运行期间配置变化造成固定数量假设。

## 指纹与身份

阵容指纹不是人员集合，而是以下有序结构的 SHA-256：

```text
area + team_num + slot + player_identity
```

这样同一批人重新分队或调整顺位也会得到新指纹。roll 使用另一份独立签名，避免把上一轮残留分组绑定到新阵容。

玩家字段清洗规则：

| 字段 | 规则 |
| --- | --- |
| steam_id | hideSteamID 必须是 17 位数字 |
| site_id | hideID 排除空、0、registered_* |
| zbj_id | hideZBJ_ID 排除空和 0，不作为唯一键 |
| nickname | NFKC 规范化后用于展示及最终兜底 |

稳定身份优先级为 steam_id、site_id、nickname。没有合法 SteamID 时 `needs_steam=true`。

## 数据模型

`draft_session`

- play_day 使用项目现有的本地时间减 3 小时口径。
- started_at、completed_at、roster_fingerprint、roll_fingerprint、team_count、status。
- status 为 complete 或 superseded。

`draft_team`

- session_id、team_num、area、roster_size、captain_nickname、group_name、roll。
- 唯一约束为 `(session_id, team_num)`。

`draft_player`

- session_id、team_num、slot、is_captain、nickname。
- steam_id、site_id、zbj_id、needs_steam、steam_id_source。
- 唯一约束为 `(session_id, team_num, slot)`。

## 公开接口与页面

公开页面：`/draft`

- 默认展示最新 complete 终稿。
- 支持比赛日和同日轮次切换。
- 每个分组展示两支队伍、roll、队长及动态选人顺位。
- 每 15 秒静默刷新；页面不可见时暂停。
- 历史浏览期间保持用户选择，不自动跳回最新。
- 公共页面只展示昵称和身份是否待补，不暴露 site_id、zbj_id 或 SteamID。

接口：`GET /api/v1/draft`

可选查询参数：

- `day=YYYYMMDD`
- `session_id=<positive integer>`

响应包含比赛日列表、当日轮次摘要和选中终稿。响应使用 `Cache-Control: no-store`，保证新终稿及时可见。

### 选手榜单的平均轮次

赛季与比赛日榜单会把 `complete` 终稿中的选人记录按 SteamID / 玩家 ID 映射到主账号，并返回 `draft_pick`：

- `average_round`：被选轮次的算术平均，`slot - 1` 即第几轮。
- `average_overall_pick`：当次所有非队长被选选手里的平均顺位。终稿没有轮内先后时间，因此同轮选手使用该轮所覆盖顺位的中点，并在界面标注为“约第 N 顺位”。
- `pick_count`：实际被选样本数，仅保留在 API 中，不在榜单展示。
- `captain_count`：担任队长的次数。队长记录不进入平均；只有队长记录的选手不显示平均轮次。
- `team_counts`：样本包含过的队伍规模，例如 8 队、10 队。
- `average_pool_position`：轮内并列取中位名次后，在当次全部非队长选手中的相对位置。它仅作为跨赛制校验与未来排序元数据，不在榜单主界面展示。

平均轮次可以直接合并 8 队与 10 队记录：每支队伍在一轮中各产生一个选择，队伍数只改变该轮包含的人数，不改变“第几轮”的含义。全场顺位则按每次选人实际人数分别计算后再取平均。榜单使用紧凑的 SVG 图标与数字：层叠图标后的 `1-2` 表示平均在第 1 至 2 轮间，选手图标后的 `≈9` 表示全场约第 9 顺位；完整文字通过悬停提示和无障碍标签提供，不显示样本次数。

参考口径：FantasyPros 将 ADP 定义为跨选秀样本的平均被选位置；NIST 的百分位说明使用秩与样本量表达相对位置，并指出并列秩可取平均。本项目保留可读的轮次作为主指标，只把并列中位秩的相对位置留在数据层。

- https://www.fantasypros.com/2020/08/fantasy-football-adp-average-draft-position-explained/
- https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/percrank.htm

## 运行

Compose 中的 `baokemeng-worker` 是独立常驻进程：

```text
python baokemeng_worker.py
```

它只负责 WSS、状态机和终稿落库，不依赖 Redis。连接失败使用带抖动的指数退避，最高等待 60 秒。

## 测试基线

- 动态 8 队、10 队和其它队数。
- 每队人数不等及 middleArea 留替补。
- 冷启动完整旧盘面不入库。
- 旧 roll 不绑定新阵容。
- 不完整 teamBat 不提交。
- 稳定等待、盘面修正、窗口内重连和重新 roll。
- roll 撤回不提交，选人后、roll 前断线不丢终稿。
- 连续轮次各自记录 started_at，重复的历史 roll 可恢复为当前版本。
- 终稿写入幂等及 superseded 关系。
- API 日期、轮次、动态人数和敏感 ID 隔离。
- 页面日期格式、轮次顺序、动态人数及路由参数。

2026-09-02 历史事件回放应只产生一份终稿：选人阵容完成于约 19:57:37，新 teamBat 出现于 19:57:44；20:08 和 20:19 重连不产生重复 session。

## 下一阶段

下一阶段再实现草稿队与 Match / MatchPlayer 的异步拟合。拟合必须使用独立进程，不阻塞监听、Flask、比赛采集、Demo 或现有 RQ worker。
