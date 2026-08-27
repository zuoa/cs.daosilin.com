<template>
  <div class="player-detail-container">
    <p v-if="error" class="empty-home">{{ error }}</p>
    <template v-else-if="player">
      <header class="player-header">
        <div class="player-info">
          <img v-if="player.avatar" :src="avatarUrl(player.avatar)" alt="" class="player-avatar">
          <div class="player-basic-info">
            <div class="name-line">
              <h1>{{ player.alias_name || player.nickname }}</h1>
              <router-link class="cup-name" :to="`/${cup}/`">{{ cupAlias }}</router-link>
            </div>
            <div class="player-id">ID · {{ player.player_id }}</div>
          </div>
          <nav class="cup-days-nav">
            <div class="cup-days-list">
              <router-link :to="`/player/${id}/${cup}/`" class="cup-day-item" :class="{ active: !day }">全部</router-link>
              <router-link
                v-for="d in cupDays"
                :key="d"
                :to="`/player/${id}/${cup}/${d}/`"
                class="cup-day-item"
                :class="{ active: d === day }"
              >{{ d }}</router-link>
            </div>
          </nav>
        </div>
      </header>

      <section class="hero-stats" v-if="stats">
        <div class="stat-strip">
          <div class="stat-strip-item">
            <div class="stat-value">{{ n2(stats.avg_pw_rating) }}</div>
            <div class="stat-label">PWR Rating</div>
            <div class="stat-rank" v-if="ranks.avg_pw_rating"><strong>#{{ ranks.avg_pw_rating }}</strong></div>
          </div>
          <div class="stat-strip-item">
            <div class="stat-value">{{ stats.match_count }}</div>
            <div class="stat-label">比赛场次</div>
          </div>
          <div class="stat-strip-item">
            <div class="stat-value">{{ pct(stats.win_rate) }}</div>
            <div class="stat-label">胜率</div>
          </div>
          <div class="stat-strip-item">
            <div class="stat-value">{{ n2(stats.kd_ratio) }}</div>
            <div class="stat-label">K/D</div>
          </div>
          <div class="stat-strip-item">
            <div class="stat-value">{{ stats.total_kills }}</div>
            <div class="stat-label">总击杀</div>
          </div>
          <div class="stat-strip-item">
            <div class="stat-value">{{ stats.total_mvp }}</div>
            <div class="stat-label">MVP</div>
          </div>
        </div>
        <div class="hexagon-wrap"><div ref="radarEl" class="hexagon-chart"></div></div>
      </section>

      <section class="section" v-if="titles.length">
        <h2 class="section-title">选手称号</h2>
        <div class="titles-chips">
          <span v-for="t in titles" :key="t.title_name" class="title-chip" :class="'title-' + t.title_type" :title="t.title_description">
            {{ t.title_name }}
          </span>
        </div>
      </section>

      <section class="section" v-if="history.length">
        <h2 class="section-title">Rating 走势</h2>
        <div ref="lineEl" style="height:260px"></div>
      </section>
    </template>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts/core'
import { LineChart, RadarChart } from 'echarts/charts'
import { GridComponent, RadarComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
echarts.use([LineChart, RadarChart, GridComponent, RadarComponent, CanvasRenderer])
import { api, avatarUrl } from '../api'

const route = useRoute()
const id = computed(() => route.params.id)
const cup = computed(() => route.params.cup || '')
const day = computed(() => route.params.day || '')
const player = ref(null)
const stats = ref(null)
const titles = ref([])
const ranks = ref({})
const cupDays = ref([])
const cupAlias = ref('')
const history = ref([])
const error = ref('')
const radarEl = ref(null)
const lineEl = ref(null)
let radarChart
let lineChart

function n2(v) { return Number(v || 0).toFixed(2) }
function pct(v) { return (Number(v || 0) * 100).toFixed(1) + '%' }

function uniqueTitles(list) {
  const seen = new Set()
  return (list || []).filter((t) => {
    if (seen.has(t.title_name)) return false
    seen.add(t.title_name)
    return true
  })
}

function draw() {
  if (radarEl.value && stats.value) {
    radarChart = radarChart || echarts.init(radarEl.value)
    radarChart.setOption({
      radar: {
        indicator: [
          { name: 'Rating', max: 2 },
          { name: 'K/D', max: 2 },
          { name: 'ADPR', max: 150 },
          { name: 'KAST', max: 100 },
          { name: 'HS%', max: 100 },
          { name: '胜率', max: 100 },
        ],
      },
      series: [{
        type: 'radar',
        data: [{
          value: [
            stats.value.avg_pw_rating || 0,
            stats.value.kd_ratio || 0,
            stats.value.avg_adpr || 0,
            (stats.value.avg_kast || 0) * (stats.value.avg_kast > 1 ? 1 : 100),
            (stats.value.avg_headshot_ratio || 0) * 100,
            (stats.value.win_rate || 0) * 100,
          ],
        }],
      }],
    })
  }
  if (lineEl.value && history.value.length) {
    lineChart = lineChart || echarts.init(lineEl.value)
    lineChart.setOption({
      xAxis: { type: 'category', data: history.value.map((h) => h.day) },
      yAxis: { type: 'value' },
      series: [{ type: 'line', data: history.value.map((h) => h.data.avg_pw_rating), smooth: true }],
    })
  }
}

async function load() {
  error.value = ''
  try {
    const data = await api.player(id.value, cup.value, day.value || null)
    player.value = data.player
    stats.value = data.player_data
    titles.value = uniqueTitles(data.titles)
    ranks.value = data.player_rankings || {}
    cupDays.value = data.cup_days || []
    cupAlias.value = data.cup_alias || data.cup
    history.value = data.historical_data || []
    document.title = `${player.value.alias_name || player.value.nickname} · ${cupAlias.value}`
    await nextTick()
    draw()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(load)
watch(() => [route.params.id, route.params.cup, route.params.day], load)
</script>
