export function n2(value) { return Number(value || 0).toFixed(2) }
export function pct(value) { return `${(Number(value || 0) * 100).toFixed(1)}%` }

const integer = (value) => value == null ? '—' : String(Math.round(Number(value)))
const decimal = (value) => value == null ? '—' : Number(value).toFixed(2)
const percentage = (value) => value == null ? '—' : `${(Number(value) * 100).toFixed(1)}%`
const seconds = (value) => value == null ? '—' : `${Number(value).toFixed(2)}s`
const money = (value) => value == null ? '—' : `$${Number(value).toFixed(0)}`

const metric = (key, label, options = {}) => ({
  key,
  label,
  direction: 'higher',
  format: decimal,
  ...options,
})

export const playerMetricGroups = [
  {
    id: 'overview', title: '核心表现', description: '先看结果，再看稳定产出。',
    metrics: [
      metric('avg_pw_rating', 'PWR Rating', { featured: true }),
      metric('match_count', '比赛场次', { featured: true, direction: 'neutral', format: integer }),
      metric('win_rate', '胜率', { featured: true, format: percentage }),
      metric('kd_ratio', 'K / D', { featured: true }),
      metric('avg_adpr', 'ADR', { featured: true }),
      metric('avg_kast', 'KAST', { featured: true, format: percentage }),
    ],
  },
  {
    id: 'firepower', title: '火力与突破', description: '输出效率、爆头倾向和开局对枪。',
    metrics: [
      metric('kills_per_round', '每回合击杀', { featured: true }),
      metric('assists_per_round', '每回合助攻', { featured: true }),
      metric('deaths_per_round', '每回合死亡', { direction: 'lower' }),
      metric('avg_headshot_ratio', '爆头率', { featured: true, format: percentage }),
      metric('fk_fd_ratio', 'FK / FD', { featured: true }),
      metric('opening_duel_win_rate', '开局对枪胜率', { featured: true, format: percentage }),
      metric('opening_duels_per_round', '开局对枪 / 回合', { direction: 'neutral' }),
      metric('total_first_kills', '首杀', { direction: 'neutral', format: integer }),
      metric('total_first_deaths', '首死', { direction: 'neutral', format: integer }),
      metric('total_snipe_num', '狙击击杀', { direction: 'neutral', format: integer }),
    ],
  },
  {
    id: 'impact', title: '多杀与残局', description: '把优势回合转化为实际影响。',
    metrics: [
      metric('multi_kill_round_rate', '多杀回合率', { featured: true, format: percentage }),
      metric('mvp_match_rate', 'MVP 场次占比', { featured: true, format: percentage }),
      metric('total_2k', '2K 回合', { direction: 'neutral', format: integer }),
      metric('total_3k', '3K 回合', { direction: 'neutral', format: integer }),
      metric('total_4k', '4K 回合', { direction: 'neutral', format: integer }),
      metric('total_5k', '5K 回合', { direction: 'neutral', format: integer }),
      metric('total_1v1', '1V1', { direction: 'neutral', format: integer }),
      metric('total_1v2', '1V2', { direction: 'neutral', format: integer }),
      metric('total_1v3', '1V3', { direction: 'neutral', format: integer }),
      metric('total_1v4', '1V4', { direction: 'neutral', format: integer }),
      metric('total_1v5', '1V5', { direction: 'neutral', format: integer }),
    ],
  },
  {
    id: 'teamwork', title: '道具与协作', description: '补枪、闪光和道具交换的质量。',
    metrics: [
      metric('trade_kill_share', '补枪击杀占比', { featured: true, format: percentage }),
      metric('utility_damage_per_round', '道具伤害 / 回合', { featured: true }),
      metric('enemy_flashes_per_round', '敌方致盲 / 回合'),
      metric('team_flash_share', '队友致盲占比', { direction: 'lower', format: percentage }),
      metric('throws_per_round', '投掷物 / 回合', { direction: 'neutral' }),
      metric('total_trade_frags', '补枪击杀', { direction: 'neutral', format: integer }),
      metric('total_utility_damage', '总道具伤害', { direction: 'neutral', format: integer }),
    ],
  },
  {
    id: 'demo', title: 'Demo 高级分析', description: '仅比较已完成 Demo 解析的样本。',
    metrics: [
      metric('demo_coverage', 'Demo 覆盖', {
        direction: 'neutral',
        get: (player) => player.demo_coverage,
        format: (value) => value ? `${value.completed || 0} / ${value.total || 0} 场` : '未覆盖',
      }),
      metric('demo_data.demo_rating', '高级 Rating', { requiresDemo: true }),
      metric('demo_data.avg_flash_thrown_per_match', '场均闪光投掷', { requiresDemo: true }),
      metric('demo_data.enemies_per_flash', '每颗闪光致盲敌人', { requiresDemo: true }),
      metric('demo_data.average_enemy_flash_seconds', '平均单次致盲', { requiresDemo: true, format: seconds }),
      metric('demo_data.avg_flash_assists_per_match', '场均闪光助攻', { requiresDemo: true }),
      metric('demo_data.utility_damage_per_throw', '道具伤害 / 投掷', { requiresDemo: true }),
      metric('demo_data.avg_unused_utility_value_per_match', '场均未用道具价值', { requiresDemo: true, direction: 'lower', format: money }),
      metric('demo_data.avg_trade_frags_per_match', '场均补枪击杀', { requiresDemo: true }),
      metric('demo_data.death_trade_rate', '被补枪率', { requiresDemo: true, format: percentage }),
      metric('demo_data.avg_clutches_won_per_match', '场均残局胜利', { requiresDemo: true }),
      metric('demo_data.opening_round_conversion', '开局击杀转回合胜率', { requiresDemo: true, format: percentage }),
      metric('demo_data.avg_team_kills_per_match', '场均队友击杀', { requiresDemo: true, direction: 'lower' }),
      metric('demo_data.ct_adr', 'CT ADR', { requiresDemo: true }),
      metric('demo_data.t_adr', 'T ADR', { requiresDemo: true }),
      metric('demo_data.ct_kast', 'CT KAST', { requiresDemo: true, format: percentage }),
      metric('demo_data.t_kast', 'T KAST', { requiresDemo: true, format: percentage }),
    ],
  },
]

export const featuredPlayerMetrics = playerMetricGroups.flatMap((group) => (
  group.metrics.filter((item) => item.featured).map((item) => ({ ...item, groupId: group.id }))
))

export function metricValue(metricDefinition, player) {
  if (!player) return null
  if (metricDefinition.get) return metricDefinition.get(player)
  return metricDefinition.key.split('.').reduce((value, key) => value?.[key], player)
}

export function formatPlayerMetric(metricDefinition, player) {
  return metricDefinition.format(metricValue(metricDefinition, player))
}

export function metricHasDifference(metricDefinition, players) {
  const values = players.map((player) => formatPlayerMetric(metricDefinition, player))
  return new Set(values).size > 1
}

export function leadingPlayerIds(metricDefinition, players) {
  if (metricDefinition.direction === 'neutral') return []
  const values = players
    .map((player) => {
      const raw = metricValue(metricDefinition, player)
      return { id: String(player.player_id), raw, value: Number(raw) }
    })
    .filter((item) => item.raw != null && Number.isFinite(item.value))
  if (!values.length) return []
  const target = metricDefinition.direction === 'lower'
    ? Math.min(...values.map((item) => item.value))
    : Math.max(...values.map((item) => item.value))
  return values.filter((item) => item.value === target).map((item) => item.id)
}

export function playerLeadMetrics(playerId, players, limit = 2) {
  return featuredPlayerMetrics
    .filter((item) => leadingPlayerIds(item, players).includes(String(playerId)))
    .slice(0, limit)
}

export function buildPlayerDetailGroups(stats) {
  const s = stats || {}
  return [
    { title: '基础数据', icon: 'activity', items: [
      { label: '比赛场次', value: s.match_count || 0 }, { label: '胜场', value: s.win_count || 0 }, { label: '胜率', value: pct(s.win_rate) },
      { label: '总回合', value: s.total_rounds || 0 }, { label: '每回合击杀', value: n2(s.kills_per_round) }, { label: '每回合死亡', value: n2(s.deaths_per_round) },
      { label: '每回合助攻', value: n2(s.assists_per_round) }, { label: '总击杀', value: s.total_kills || 0 }, { label: '总助攻', value: s.total_assists || 0 },
    ] },
    { title: '击杀效率', icon: 'target', items: [
      { label: '首杀 / 首死', value: `${s.total_first_kills || 0} / ${s.total_first_deaths || 0}` }, { label: 'FK / FD', value: n2(s.fk_fd_ratio) },
      { label: '开局对枪胜率', value: pct(s.opening_duel_win_rate) }, { label: '开局对枪/回合', value: n2(s.opening_duels_per_round) },
      { label: '爆头数', value: s.total_headshots || 0 }, { label: '爆头率', value: pct(s.avg_headshot_ratio) }, { label: 'K / D', value: n2(s.kd_ratio) },
    ] },
    { title: '多杀与残局', icon: 'trophy', items: [
      { label: '2K / 3K', value: `${s.total_2k || 0} / ${s.total_3k || 0}` }, { label: '4K / 5K', value: `${s.total_4k || 0} / ${s.total_5k || 0}` },
      { label: '多杀回合', value: s.multi_kill_rounds || 0 }, { label: '多杀回合率', value: pct(s.multi_kill_round_rate) },
      { label: '1V1 / 1V2', value: `${s.total_1v1 || 0} / ${s.total_1v2 || 0}` }, { label: '1V3 / 1V4 / 1V5', value: `${s.total_1v3 || 0} / ${s.total_1v4 || 0} / ${s.total_1v5 || 0}` },
    ] },
    { title: '高级数据', icon: 'database', items: [
      { label: 'PWR Rating', value: n2(s.avg_pw_rating) }, { label: 'RWS', value: n2(s.avg_rws) }, { label: 'WE', value: n2(s.avg_we) },
      { label: 'ADR（回合加权）', value: n2(s.avg_adpr) }, { label: 'KAST', value: pct(s.avg_kast) }, { label: '比赛 MVP', value: s.match_mvp_count || 0 },
      { label: 'MVP 场次占比', value: pct(s.mvp_match_rate) }, { label: '狙击击杀', value: s.total_snipe_num || 0 },
    ] },
    { title: '投掷物', icon: 'layers', items: [
      { label: '敌方致盲', value: s.total_flash_success || 0 }, { label: '敌方致盲/回合', value: n2(s.enemy_flashes_per_round) },
      { label: '队友致盲', value: s.total_flash_teammate || 0 }, { label: '队友致盲占比', value: pct(s.team_flash_share) },
      { label: '投掷物总数', value: s.total_throws_count || 0 }, { label: '投掷物/回合', value: n2(s.throws_per_round) },
      { label: '手雷伤害', value: s.total_grenade_damage || 0 }, { label: '燃烧伤害', value: s.total_inferno_damage || 0 },
      { label: '道具伤害/回合', value: n2(s.utility_damage_per_round) },
    ] },
    { title: '团队协作', icon: 'users', items: [
      { label: '补枪击杀', value: s.total_trade_frags || 0 }, { label: '补枪击杀占比', value: pct(s.trade_kill_share) },
      { label: '总道具伤害', value: s.total_utility_damage || 0 },
    ] },
  ]
}
