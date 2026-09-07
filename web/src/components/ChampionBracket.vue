<template>
  <section class="champion-bracket" aria-labelledby="champion-bracket-title">
    <section
      v-if="bracket?.champion_team"
      class="champion-stage"
      aria-labelledby="daily-champion-title"
    >
      <div class="champion-stage-mark" aria-hidden="true">
        <AppIcon name="trophy" :size="50" />
      </div>
      <div class="champion-stage-copy">
        <span>{{ formattedDay }} 当日冠军</span>
        <h2 id="daily-champion-title">{{ bracket.champion_team }}</h2>
        <p v-if="finalSummary">{{ finalSummary }}</p>
      </div>
      <div class="champion-roster-panel">
        <div class="champion-roster-heading">
          <h3>冠军名单</h3>
          <span>{{ championRoster.length || 0 }} 名选手</span>
        </div>
        <ul v-if="championRoster.length" class="champion-roster-list">
          <li
            v-for="(player, index) in championRoster"
            :key="player.player_id"
            :style="{ '--roster-index': index }"
          >
            <PlayerAvatar
              :src="player.avatar"
              :name="playerName(player)"
              class="champion-roster-avatar"
            />
            <strong>{{ playerName(player) }}</strong>
            <small v-if="player.alias_name && player.nickname && player.alias_name !== player.nickname">
              {{ player.nickname }}
            </small>
          </li>
        </ul>
        <p v-else class="champion-roster-pending">冠军名单正在确认</p>
      </div>
    </section>

    <header class="champion-bracket-heading">
      <div>
        <h2 id="champion-bracket-title">夺冠晋级路线</h2>
        <p>每组为 BO3，胜者沿连线进入下一轮。</p>
      </div>
      <div v-if="bracket?.champion_team" class="bracket-result" aria-label="当日冠亚军">
        <span>冠军</span><strong>{{ bracket.champion_team }}</strong>
        <small>亚军 {{ bracket.runner_up_team }}</small>
      </div>
      <span v-else class="bracket-status">{{ hasSeries ? '赛程进行中' : '等待首组 BO3 完赛' }}</span>
    </header>

    <div class="bracket-scroll" tabindex="0" aria-label="横向滚动查看完整晋级路线">
      <div class="bracket-canvas">
        <section
          v-for="round in normalizedRounds"
          :key="round.key"
          class="bracket-round"
          :class="`bracket-round-${round.key}`"
          :aria-labelledby="`bracket-round-${round.key}`"
        >
          <h3 :id="`bracket-round-${round.key}`">{{ round.label }}</h3>
          <div class="bracket-round-track">
            <article
              v-for="slot in round.slots"
              :key="`${round.key}-${slot.row}`"
              class="bracket-match"
              :class="{ pending: !slot.series, decided: slot.series }"
              :style="{ gridRow: slot.row }"
              :aria-label="seriesLabel(slot.series, round.key)"
            >
              <template v-if="slot.series">
                <div
                  v-for="team in slot.series.teams"
                  :key="team.name"
                  class="bracket-team"
                  :class="{ winner: team.winner }"
                >
                  <span>{{ team.name }}</span>
                  <strong>{{ team.score }}</strong>
                </div>
              </template>
              <div v-else class="bracket-pending-copy">
                <span>{{ pendingLabel(round.key) }}</span><small>BO3</small>
              </div>
            </article>
          </div>
        </section>

        <div class="bracket-links bracket-links-opening" aria-hidden="true">
          <span></span><span></span>
        </div>
        <div class="bracket-links bracket-links-final" aria-hidden="true"><span></span></div>
      </div>
    </div>
    <p class="bracket-scroll-hint">窄屏可横向滑动查看完整路线</p>
  </section>
</template>

<script setup>
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import PlayerAvatar from './PlayerAvatar.vue'

const props = defineProps({
  bracket: { type: Object, default: null },
  championRoster: { type: Array, default: () => [] },
  day: { type: String, default: '' },
})

const expectedRounds = [
  { key: 'opening', label: '首轮', rows: [1, 3, 5, 7] },
  { key: 'qualification', label: '晋级轮', rows: [2, 6] },
  { key: 'final', label: '冠军战', rows: [4] },
]

const normalizedRounds = computed(() => expectedRounds.map((expected) => {
  const source = props.bracket?.rounds?.find((round) => round.key === expected.key)
  return {
    ...expected,
    slots: expected.rows.map((row, index) => ({ row, series: source?.series?.[index] || null })),
  }
}))

const hasSeries = computed(() => normalizedRounds.value.some(
  (round) => round.slots.some((slot) => slot.series),
))

const formattedDay = computed(() => {
  const digits = String(props.day || '').replace(/\D/g, '')
  if (digits.length !== 8) return props.day || '本日'
  return `${digits.slice(0, 4)}.${digits.slice(4, 6)}.${digits.slice(6, 8)}`
})

const finalSummary = computed(() => {
  const final = props.bracket?.rounds?.find((round) => round.key === 'final')?.series?.[0]
  if (!final?.teams?.length) return ''
  const champion = final.teams.find((team) => team.winner)
  const runnerUp = final.teams.find((team) => !team.winner)
  if (!champion || !runnerUp) return ''
  return `冠军战 ${champion.score}:${runnerUp.score} 战胜 ${runnerUp.name}`
})

function pendingLabel(roundKey) {
  return roundKey === 'opening' ? '等待对阵' : '待晋级'
}

function seriesLabel(series, roundKey) {
  if (!series) return `${pendingLabel(roundKey)}，BO3`
  const [left, right] = series.teams
  return `${left.name} ${left.score} 比 ${right.score} ${right.name}，${left.winner ? left.name : right.name} 晋级`
}

function playerName(player) {
  return player.alias_name || player.nickname || player.player_id
}
</script>
