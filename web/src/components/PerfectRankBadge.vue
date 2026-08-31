<template>
  <span
    class="perfect-rank-badge"
    :class="[rankClass, sTierClass, { 'rank-elite': isElite, 'show-details': showDetails, large, compact }]"
    :aria-label="ariaLabel"
    :title="title"
  >
    <i v-if="rankClass === 'rank-s'" class="rank-emblem" aria-hidden="true">
      <i class="rank-aura"></i>
      <strong>{{ normalizedLevel }}</strong>
    </i>
    <template v-else>
      <i class="rank-aura" aria-hidden="true"></i>
      <strong>{{ normalizedLevel }}</strong>
    </template>
    <span v-if="displayLabel" :class="{ 'rank-detail': showDetails && rankClass === 'rank-s' }">{{ displayLabel }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  level: { type: String, default: '' },
  score: { type: [Number, String], default: 0 },
  stars: { type: [Number, String], default: null },
  updatedAt: { type: String, default: '' },
  showDetails: { type: Boolean, default: false },
  large: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})

const numericScore = computed(() => Number(props.score || 0))
const numericStars = computed(() => {
  if (props.stars === null || props.stars === undefined || props.stars === '') return null
  const value = Number(props.stars)
  return Number.isFinite(value) ? Math.max(0, Math.round(value)) : null
})
const normalizedLevel = computed(() => numericScore.value > 0 ? (props.level || '未定级') : '未定级')
const isElite = computed(() => normalizedLevel.value.startsWith('精英'))
const rankClass = computed(() => {
  const level = normalizedLevel.value.toUpperCase()
  if (level.startsWith('S')) return 'rank-s'
  if (level.includes('A')) return 'rank-a'
  if (level.includes('B')) return 'rank-b'
  if (level.includes('C')) return 'rank-c'
  return 'rank-d'
})
const sTier = computed(() => {
  if (rankClass.value !== 'rank-s' || numericStars.value === null) return 'standard'
  if (numericStars.value >= 50) return 'demon'
  if (numericStars.value >= 25) return 'diamond'
  if (numericStars.value >= 11) return 'gold'
  return 'standard'
})
const sTierClass = computed(() => rankClass.value === 'rank-s' ? `s-tier-${sTier.value}` : '')
const sTierName = computed(() => ({
  standard: '普通 S',
  gold: '黄金 S',
  diamond: '钻石 S',
  demon: '魔王 S',
})[sTier.value])
const scoreLabel = computed(() => {
  if (numericScore.value <= 0) return ''
  if (rankClass.value === 'rank-s') {
    if (numericStars.value !== null) return ''
    return numericScore.value === 2401 ? '2401+' : `${Math.round(numericScore.value)}`
  }
  return `${Math.round(numericScore.value)}`
})
const displayLabel = computed(() => {
  if (!props.showDetails || rankClass.value !== 'rank-s' || numericScore.value <= 0) {
    return scoreLabel.value
  }
  const score = `${Math.round(numericScore.value)} 分`
  return numericStars.value === null ? score : `${score} · ${numericStars.value} 星`
})
const ariaLabel = computed(() => {
  if (numericScore.value <= 0) return '完美平台段位未定级'
  if (rankClass.value === 'rank-s' && numericStars.value !== null) {
    const score = props.showDetails ? `，天梯分 ${Math.round(numericScore.value)}` : ''
    return `完美平台段位 ${sTierName.value}${score}，${numericStars.value} 星`
  }
  return `完美平台段位 ${normalizedLevel.value}，天梯分 ${scoreLabel.value}`
})
const title = computed(() => {
  if (!props.updatedAt) return ariaLabel.value
  return `${ariaLabel.value} · 更新于 ${String(props.updatedAt).replace('T', ' ').slice(0, 16)}`
})
</script>
