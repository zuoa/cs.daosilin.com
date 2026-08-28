<template>
  <span
    class="perfect-rank-badge"
    :class="[rankClass, { 'rank-elite': isElite, large, compact }]"
    :aria-label="ariaLabel"
    :title="title"
  >
    <i class="rank-aura" aria-hidden="true"></i>
    <small>PW</small>
    <strong>{{ normalizedLevel }}</strong>
    <span>{{ scoreLabel }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  level: { type: String, default: '' },
  score: { type: [Number, String], default: 0 },
  updatedAt: { type: String, default: '' },
  large: { type: Boolean, default: false },
  compact: { type: Boolean, default: false },
})

const normalizedLevel = computed(() => props.level || '未定级')
const isElite = computed(() => normalizedLevel.value.startsWith('精英'))
const rankClass = computed(() => {
  const level = normalizedLevel.value.toUpperCase()
  if (level.startsWith('S')) return 'rank-s'
  if (level.includes('A')) return 'rank-a'
  if (level.includes('B')) return 'rank-b'
  if (level.includes('C')) return 'rank-c'
  return 'rank-d'
})
const numericScore = computed(() => Number(props.score || 0))
const scoreLabel = computed(() => {
  if (numericScore.value <= 0) return '未定级'
  return rankClass.value === 'rank-s' && numericScore.value === 2401
    ? '2401+ 分'
    : `${Math.round(numericScore.value)} 分`
})
const ariaLabel = computed(() => `完美平台段位 ${normalizedLevel.value}，${scoreLabel.value}`)
const title = computed(() => {
  if (!props.updatedAt) return ariaLabel.value
  return `${ariaLabel.value} · 更新于 ${String(props.updatedAt).replace('T', ' ').slice(0, 16)}`
})
</script>
