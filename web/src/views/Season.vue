<template>
  <div class="container">
    <header class="header">
      <div class="header-title">
        <p class="eyebrow"><router-link to="/">全部赛季</router-link></p>
        <h1 class="title">
          <router-link :to="`/${cup}/`">{{ cupAlias }}</router-link>
        </h1>
        <p v-if="day" class="subtitle">{{ day }} 数据统计</p>
      </div>
      <div v-if="lastCrawl" class="header-meta">数据更新 · {{ lastCrawl }}</div>
    </header>

    <nav class="cup-days-container">
      <div class="cup-days-list">
        <router-link :to="`/${cup}/`" class="cup-day-item" :class="{ active: !day }">
          <span class="day-number">∞</span>
          <span class="day-name">全部</span>
        </router-link>
        <router-link
          v-for="(d, i) in cupDays"
          :key="d"
          :to="`/${cup}/${d}/`"
          class="cup-day-item"
          :class="{ active: d === day }"
        >
          <span class="day-number">{{ i + 1 }}</span>
          <span class="day-name">{{ d }}</span>
        </router-link>
      </div>
    </nav>

    <main class="table-container">
      <p v-if="error">{{ error }}</p>
      <table v-else class="stats-table">
        <thead>
          <tr>
            <th>#</th>
            <th>选手</th>
            <th v-if="day">称号</th>
            <th>赛季奖杯</th>
            <th>场次</th>
            <th>胜场</th>
            <th>胜率</th>
            <th>K/D</th>
            <th>Rating</th>
            <th>ADPR</th>
            <th>WE</th>
            <th>爆头率</th>
            <th>MVP轮</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="(p, idx) in players" :key="p.player_id">
            <tr class="cursor" @click="open = open === idx ? -1 : idx">
              <td>{{ idx + 1 }}</td>
              <td>
                <div class="player-name">
                  <img v-if="p.avatar" :src="avatarUrl(p.avatar)" alt="" class="player-avatar" @error="hideImg">
                  <span class="player-name-text">{{ p.alias_name || p.nickname }}</span>
                  <span v-if="day && p.team_name" class="team-tag">{{ p.team_name }}</span>
                </div>
              </td>
              <td v-if="day">
                <div class="title-container">
                  <span
                    v-for="t in uniqueTitles(p.titles).slice(0, 2)"
                    :key="t.title_name"
                    class="title-badge"
                    :class="'title-' + t.title_type"
                    :title="t.title_description"
                  >{{ t.title_name }}</span>
                  <span v-if="uniqueTitles(p.titles).length > 2" class="title-more">+{{ uniqueTitles(p.titles).length - 2 }}</span>
                </div>
              </td>
              <td>
                <div class="trophy-container">
                  <span v-for="(tr, ti) in p.trophy_history || []" :key="ti" :title="tr.day + (tr.trophy === 'champion' ? ' 冠军' : ' 亚军')">
                    {{ tr.trophy === 'champion' ? '冠' : '亚' }}
                  </span>
                </div>
              </td>
              <td>{{ p.match_count }}</td>
              <td>{{ p.win_count }}</td>
              <td><span :class="{ 'stat-good': p.win_rate >= 0.6 }">{{ pct(p.win_rate) }}</span></td>
              <td>{{ n2(p.kd_ratio) }}</td>
              <td><span :class="{ 'stat-strong': p.avg_pw_rating >= 1.57 }">{{ n2(p.avg_pw_rating) }}</span></td>
              <td>{{ n2(p.avg_adpr) }}</td>
              <td>{{ n2(p.avg_we) }}</td>
              <td>{{ pct(p.avg_headshot_ratio) }}</td>
              <td>{{ p.total_mvp }}</td>
              <td>
                <router-link
                  class="detail-button"
                  :to="`/player/${p.player_id}/${cup}${day ? '/' + day : ''}/`"
                  @click.stop
                >详情</router-link>
              </td>
            </tr>
            <tr v-if="open === idx" class="drawer open">
              <td :colspan="day ? 14 : 13">
                <div class="drawer-content">
                  <div v-if="uniqueTitles(p.titles).length" class="drawer-section">
                    <h4>称号信息</h4>
                    <div class="titles-grid">
                      <div v-for="t in uniqueTitles(p.titles)" :key="t.title_name" class="title-card" :class="'title-' + t.title_type">
                        <div class="title-name">{{ t.title_name }}</div>
                        <div class="title-description">{{ t.title_description }}</div>
                      </div>
                    </div>
                  </div>
                  <div class="drawer-section">
                    <h4>基础数据</h4>
                    <div class="drawer-item"><span class="drawer-label">胜场</span><span class="drawer-value highlight">{{ p.win_count }}</span></div>
                    <div class="drawer-item"><span class="drawer-label">胜率</span><span class="drawer-value">{{ pct(p.win_rate) }}</span></div>
                    <div class="drawer-item"><span class="drawer-label">首杀 / 首死</span><span class="drawer-value">{{ p.total_first_kills }} / {{ p.total_first_deaths }}</span></div>
                    <div class="drawer-item"><span class="drawer-label">2K / 3K / 4K / 5K</span><span class="drawer-value">{{ p.total_2k }} / {{ p.total_3k }} / {{ p.total_4k }} / {{ p.total_5k }}</span></div>
                    <div class="drawer-item"><span class="drawer-label">1v2 / 1v3 / 1v4 / 1v5</span><span class="drawer-value">{{ p.total_1v2 }} / {{ p.total_1v3 }} / {{ p.total_1v4 }} / {{ p.total_1v5 }}</span></div>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, avatarUrl } from '../api'

const route = useRoute()
const cup = computed(() => route.params.cup)
const day = computed(() => route.params.day || '')
const cupAlias = ref('')
const players = ref([])
const cupDays = ref([])
const lastCrawl = ref('')
const error = ref('')
const open = ref(-1)

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
function hideImg(e) { e.target.style.display = 'none' }

async function load() {
  error.value = ''
  open.value = -1
  try {
    const data = await api.cup(cup.value, day.value || null)
    cupAlias.value = data.cup_alias || data.cup
    players.value = data.players || []
    cupDays.value = data.cup_days || []
    lastCrawl.value = data.last_crawl_time || ''
    document.title = `${cupAlias.value} ${day.value || ''}`.trim()
  } catch (e) {
    error.value = e.message
  }
}

onMounted(load)
watch(() => [route.params.cup, route.params.day], load)
</script>
