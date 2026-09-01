<template>
  <article ref="cardEl" class="player-showcase-card" :class="{ 'poster-mode': poster }">
    <div class="showcase-concrete" aria-hidden="true"></div>
    <div class="showcase-red-block" aria-hidden="true"></div>
    <header class="showcase-brandline">
      <span class="showcase-mark"><AppIcon name="target" :size="poster ? 26 : 20" /></span>
      <strong>熊掌CS Major</strong>
      <span>PLAYER INTELLIGENCE</span>
    </header>

    <img
      v-if="poster && qrCode"
      class="showcase-qr-code"
      :src="qrCode"
      alt=""
    >

    <div class="showcase-portrait" :style="portraitStyle">
      <img class="portrait-transform-image" :src="portrait.url" :alt="`${name} 人物展示照`" crossorigin="anonymous">
    </div>

    <div class="showcase-identity">
      <div class="showcase-rating">
        <span>PWR RATING</span>
        <strong>{{ rating }}</strong>
      </div>
      <div class="showcase-name">
        <h1>{{ name }}</h1>
        <p>{{ scopeLabel }}</p>
      </div>
      <div v-if="hasPerfectRank" class="showcase-rank">
        <span>{{ perfectLevel || 'PWR' }}</span>
        <strong>{{ perfectScore || rating }}</strong>
        <small>PERFECT WORLD</small>
      </div>
    </div>

    <dl class="showcase-metrics">
      <div v-for="metric in metrics" :key="metric.label">
        <dt><AppIcon :name="metric.icon" :size="poster ? 24 : 18" />{{ metric.label }}</dt>
        <dd>{{ metric.value }}</dd>
      </div>
    </dl>

    <footer class="showcase-footer">
      <span>{{ footerScope }}</span>
      <strong>TACTICAL PLAYER DOSSIER</strong>
    </footer>
  </article>
</template>

<script setup>
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  name: { type: String, required: true },
  season: { type: String, default: '' },
  day: { type: String, default: '' },
  portrait: { type: Object, required: true },
  rating: { type: String, default: '0.00' },
  perfectLevel: { type: String, default: '' },
  perfectScore: { type: [String, Number], default: '' },
  metrics: { type: Array, default: () => [] },
  poster: { type: Boolean, default: false },
  qrCode: { type: String, default: '' },
})

const cardEl = ref(null)
const scopeLabel = computed(() => [props.season, props.day].filter(Boolean).join(' / ') || '赛季档案')
const footerScope = computed(() => props.day || props.season || 'CS PLAYER')
const hasPerfectRank = computed(() => {
  const level = String(props.perfectLevel || '').trim()
  return Number(props.perfectScore) > 0 && level && !['未定位', '未定级'].includes(level)
})
const portraitStyle = computed(() => ({
  '--portrait-scale': Number(props.portrait?.scale || 1),
  '--portrait-x': `${Number(props.portrait?.offset_x || 0)}%`,
  '--portrait-y': `${Number(props.portrait?.offset_y || 0)}%`,
}))

defineExpose({ getElement: () => cardEl.value })
</script>
