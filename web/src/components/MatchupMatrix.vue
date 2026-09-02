<template>
  <section class="matchup-panel" aria-labelledby="matchup-matrix-title">
    <header class="matchup-header">
      <div>
        <h3 id="matchup-matrix-title">选手对位矩阵</h3>
        <p>以行选手为视角，比分左侧为击杀，右侧为被杀。</p>
      </div>
      <div class="matchup-legend" aria-label="对位结果图例">
        <span class="win">胜</span><span class="draw">平</span><span class="loss">负</span>
      </div>
    </header>

    <div v-if="players.length < 2 || !hasMatchupData" class="empty-state compact">
      <span><AppIcon name="target" /></span>
      <h3>暂无对位数据</h3>
      <p>{{ players.length < 2 ? '至少需要两名选手才能生成对位矩阵。' : '这场比赛没有可用的选手击杀明细。' }}</p>
    </div>

    <div v-else class="matchup-scroll" @mouseleave="hoveredColumn = ''">
      <table class="matchup-table">
        <caption class="sr-only">选手对位矩阵。每个单元格按行选手视角显示击杀数比被杀数。</caption>
        <thead>
          <tr>
            <th class="matrix-corner" scope="col">选手 / 对手</th>
            <th
              v-for="opponent in players"
              :key="opponent.player_id"
              class="matrix-player-heading"
              :class="{
                active: hoveredColumn === String(opponent.player_id),
                current: isCurrent(opponent),
              }"
              scope="col"
            >
              <span>{{ playerName(opponent) }}</span>
              <small>{{ teamLabel(opponent) }}</small>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="rowPlayer in players" :key="rowPlayer.player_id">
            <th class="matrix-row-heading" :class="{ current: isCurrent(rowPlayer) }" scope="row">
              <span>{{ playerName(rowPlayer) }}</span>
              <small>{{ teamLabel(rowPlayer) }}</small>
            </th>
            <td
              v-for="opponent in players"
              :key="opponent.player_id"
              class="matchup-cell"
              :class="[
                outcome(rowPlayer, opponent),
                { active: hoveredColumn === String(opponent.player_id) },
              ]"
              :aria-label="cellLabel(rowPlayer, opponent)"
              @mouseenter="hoveredColumn = String(opponent.player_id)"
            >
              <template v-if="samePlayer(rowPlayer, opponent)">
                <strong aria-hidden="true">-</strong><small>本人</small>
              </template>
              <template v-else-if="sameTeam(rowPlayer, opponent)">
                <strong aria-hidden="true">-</strong><small>同队</small>
              </template>
              <template v-else>
                <strong>{{ duel(rowPlayer, opponent).kills }} : {{ duel(rowPlayer, opponent).deaths }}</strong>
                <small>{{ outcomeLabel(rowPlayer, opponent) }}</small>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  players: { type: Array, default: () => [] },
  matrix: { type: Object, default: () => ({}) },
  currentPlayerId: { type: [String, Number], default: '' },
})

const hoveredColumn = ref('')
const hasMatchupData = computed(() => props.players.some((player) => (
  props.players.some((opponent) => {
    if (samePlayer(player, opponent) || sameTeam(player, opponent)) return false
    const value = duel(player, opponent)
    return value.kills + value.deaths > 0
  })
)))

function playerName(player) {
  return player?.alias_name || player?.nickname || player?.player_id || '未知选手'
}
function teamLabel(player) {
  const team = Number(player?.team)
  if (team === 1) return player?.team_name || '队伍 A'
  if (team === 2) return player?.team_name || '队伍 B'
  return player?.team_name || '未分队'
}
function samePlayer(player, opponent) {
  return String(player?.player_id) === String(opponent?.player_id)
}
function sameTeam(player, opponent) {
  const playerTeam = Number(player?.team)
  const opponentTeam = Number(opponent?.team)
  return playerTeam > 0 && playerTeam === opponentTeam
}
function isCurrent(player) {
  return props.currentPlayerId !== '' && String(player?.player_id) === String(props.currentPlayerId)
}
function duel(player, opponent) {
  const value = props.matrix?.[String(player?.player_id)]?.[String(opponent?.player_id)] || {}
  return {
    kills: Math.max(0, Number(value.kills) || 0),
    deaths: Math.max(0, Number(value.deaths) || 0),
  }
}
function outcome(player, opponent) {
  if (samePlayer(player, opponent)) return 'self'
  if (sameTeam(player, opponent)) return 'teammate'
  const value = duel(player, opponent)
  if (value.kills + value.deaths === 0) return 'none'
  if (value.kills > value.deaths) return 'win'
  if (value.kills < value.deaths) return 'loss'
  return 'draw'
}
function outcomeLabel(player, opponent) {
  return ({ win: '胜', loss: '负', draw: '平', none: '无交手' }[outcome(player, opponent)] || '')
}
function cellLabel(player, opponent) {
  const rowName = playerName(player)
  const opponentName = playerName(opponent)
  if (samePlayer(player, opponent)) return `${rowName} 本人`
  if (sameTeam(player, opponent)) return `${rowName} 与 ${opponentName} 同队`
  const value = duel(player, opponent)
  return `${rowName} 对 ${opponentName}，${value.kills} 比 ${value.deaths}，${outcomeLabel(player, opponent)}`
}
</script>

<style scoped>
.matchup-panel { overflow: hidden; border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface); }
.matchup-header { display: flex; min-height: 68px; align-items: center; justify-content: space-between; gap: 18px; border-bottom: 1px solid var(--line); padding: 13px 15px; }
.matchup-header h3 { font-family: var(--font-display); font-size: .96rem; }
.matchup-header p { margin-top: 3px; color: var(--ink-500); font-size: .7rem; }
.matchup-legend { display: flex; align-items: center; gap: 5px; }
.matchup-legend span { min-width: 28px; border: 1px solid var(--line); border-radius: 6px; padding: 3px 6px; font-family: var(--font-mono); font-size: .62rem; font-weight: 800; text-align: center; }
.matchup-legend .win { border-color: var(--color-accent-line); background: var(--signal-soft); color: var(--signal-dark); }
.matchup-legend .draw { background: var(--surface-soft); color: var(--ink-600); }
.matchup-legend .loss { border-color: var(--color-danger-line); background: var(--danger-soft); color: var(--danger-dark); }
.matchup-scroll { position: relative; max-width: 100%; overflow: auto; scrollbar-color: var(--line-strong) transparent; }
.matchup-table { width: max-content; min-width: 100%; border-collapse: separate; border-spacing: 0; font-variant-numeric: tabular-nums; }
.matchup-table th, .matchup-table td { border-right: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.matchup-table tr:last-child > * { border-bottom: 0; }
.matchup-table tr > *:last-child { border-right: 0; }
.matrix-corner, .matrix-row-heading { position: sticky; left: 0; width: 132px; min-width: 132px; max-width: 132px; background: var(--surface); text-align: left; }
.matrix-corner { z-index: 3; top: 0; height: 58px; padding: 9px 11px; color: var(--ink-500); font-size: .62rem; }
.matrix-player-heading { position: sticky; z-index: 2; top: 0; width: 82px; min-width: 82px; height: 58px; padding: 7px 6px; background: var(--surface); text-align: center; transition: background-color var(--dur-micro) var(--ease-out); }
.matrix-row-heading { z-index: 1; height: 62px; padding: 8px 11px; box-shadow: 1px 0 var(--line); }
.matrix-player-heading span, .matrix-row-heading span { display: block; overflow: hidden; color: var(--ink-800); font-size: .7rem; font-weight: 750; text-overflow: ellipsis; white-space: nowrap; }
.matrix-player-heading small, .matrix-row-heading small { display: block; overflow: hidden; margin-top: 2px; color: var(--ink-500); font-size: .58rem; font-weight: 500; text-overflow: ellipsis; white-space: nowrap; }
.matrix-player-heading.current, .matrix-row-heading.current { box-shadow: inset 3px 0 var(--signal); }
.matrix-player-heading.active { background: var(--color-accent-faint); }
.matchup-table tbody tr:hover .matrix-row-heading { background: var(--color-accent-faint); }
.matchup-cell { width: 82px; min-width: 82px; height: 62px; padding: 7px 5px; background: var(--surface); text-align: center; transition: background-color var(--dur-micro) var(--ease-out); }
.matchup-cell strong { display: block; color: var(--ink-700); font-family: var(--font-mono); font-size: .76rem; line-height: 1.2; }
.matchup-cell small { display: block; margin-top: 3px; color: var(--ink-500); font-size: .57rem; }
.matchup-cell.win { background: var(--signal-soft); }
.matchup-cell.win strong, .matchup-cell.win small { color: var(--signal-dark); }
.matchup-cell.loss { background: var(--danger-soft); }
.matchup-cell.loss strong, .matchup-cell.loss small { color: var(--danger-dark); }
.matchup-cell.draw { background: var(--amber-soft); }
.matchup-cell.draw strong, .matchup-cell.draw small { color: var(--ink-700); }
.matchup-cell.self, .matchup-cell.teammate { background: var(--surface-soft); }
.matchup-cell.self strong, .matchup-cell.teammate strong { color: var(--ink-400); }
.matchup-cell.active:not(.win):not(.loss):not(.draw) { background: var(--color-accent-faint); }

@media (max-width: 45rem) {
  .matchup-header { align-items: flex-start; flex-direction: column; gap: 9px; }
  .matrix-corner, .matrix-row-heading { width: 116px; min-width: 116px; max-width: 116px; }
  .matrix-player-heading, .matchup-cell { width: 76px; min-width: 76px; }
}
</style>
