# Demo 异步分析

## 数据链路

比赛先按原有 WMPVP 接口写入，页面可立即显示基础统计。Demo 是不阻塞采集的第二阶段：调度器将最近 30 天的新比赛写入持久化任务表并投递到 Redis，单并发 `demo-worker` 下载、校验、解析后再发布事件指标。

数据库是任务状态的事实来源，Redis 只负责执行。状态包括：`pending`、`queued`、`downloading`、`validating`、`parsing`、`completed`、`unavailable`、`blocked_credentials`、`failed`。任务 ID 使用 `demo:{match_id}:{metric_version}`，重复扫描不会并发解析同一版本。

失败任务按 1 分钟、10 分钟、1 小时由 RQ 有界重试；上游不存在/过期和凭证失效不会盲目重试。管理员可在「API 与安全」查看状态并手动重试。

## 部署

1. 在 `.env` 配置 WMPVP 采集及 Demo 下载的默认凭证：

   ```text
   WMPVP_ACCESS_TOKEN=<PWA access token>
   WMPVP_STEAM_ID=<SteamID64>
   ```

2. 登录管理后台，在「API 与安全」中开启 Demo 分析。启停状态保存在数据库中，不需要配置启用环境变量。

3. 如果需要在后台保存另一套覆盖凭证，再生成专用 Fernet key：

   ```bash
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   并在部署环境设置：

   ```text
   DEMO_CREDENTIAL_ENCRYPTION_KEY=<Fernet key>
   ```

4. 使用同一镜像启动 `app` 与 `demo-worker`。`docker-compose.yml` 已为两者挂载同一个 `/data`，归档默认写入 `/data/demos`。后台开启后会自动扫描新比赛和最近 30 天。

凭证优先级为“管理后台加密凭证 → `.env` 中的 `WMPVP_ACCESS_TOKEN` / `WMPVP_STEAM_ID`”。没有加密 key 时后台拒绝保存覆盖凭证；access token 不进入日志、任务参数、下载归档或 API 返回。数据库中没有保存凭证时，Worker 自动回退到 `.env`。

## 下载与校验

- 下载适配器固定使用 `cs-demo-downloader==1.3.0`，Docker 的 CPython 3.12 Linux 环境可加载其配套 PWA signer。
- 单个下载与解压后文件均限制为 1 GiB。
- 解析前校验 `PBDEMS2` header；解析后校验地图、有效回合以及至少 80% 的阵容 SteamID。
- 原始 Demo 计算 SHA-256 后以 `match.dem.zst` 内容寻址长期保存；解析器原始 JSON 以 `analysis-v1.json.zst` 同目录保存。
- 解析器固定为 `cs2-analyser-tool` commit `88cb54ea0267fc8f4a8ae8d03987b50aec2a0653`，由 Docker 多阶段构建的非交互 JSON adapter 调用。

## 统计口径

一个比赛完成 Demo 分析后，K/D/A、ADR、KAST、开局、多杀、补枪、道具伤害等通用字段以该场 Demo 为准；尚未完成的比赛继续使用平台值，跨场聚合从原始计数和回合数重新加权。`platform_data` 始终保留原平台聚合，`demo_data` 只汇总完成 Demo 的场次，`metric_source` 为 `platform`、`mixed` 或 `demo`。

Demo 专属指标的分母只包含已完成 Demo，缺失不等于 0。`demo_coverage` 返回 `completed`、`total`、`ratio`，前端以 `X/Y` 显示覆盖率。

首期事件指标包括补枪/被补枪、闪光投掷与敌友致盲、去重致盲时长、六类投掷物、HE/火焰伤害、未使用道具价值、多杀/ACE、残局、开局对枪及转化、CT/T 分边数据、武器击杀和队友击杀。`demo_rating` 与六项子评分是实验性近似 Rating 3.0，明确不替代 PWR。
