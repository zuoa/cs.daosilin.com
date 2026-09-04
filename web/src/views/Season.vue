<template>
  <div class="public-site season-page">
    <header class="public-nav compact-nav">
      <router-link class="public-brand" to="/" aria-label="返回数据首页">
        <span class="brand-mark"><AppIcon name="target" :size="22" /></span>
        <span><strong>熊掌CS Major</strong><small>COMPETITIVE ARCHIVE</small></span>
      </router-link>
      <nav aria-label="赛季页面导航"><router-link to="/"><AppIcon name="layers" />全部赛季</router-link></nav>
    </header>

    <main>
      <section class="season-hero">
        <div class="season-title-block">
          <h1>{{ cupAlias || cup }}</h1>
          <p>{{ day ? `${day} · 当日选手数据` : '赛季综合数据与选手排名' }}</p>
        </div>
        <div class="season-summary" aria-label="赛季数据概览">
          <div><span>选手</span><strong>{{ players.length }}</strong></div>
          <div><span>最高 Rating</span><strong>{{ topRating }}</strong></div>
          <div><span>平均 Rating</span><strong>{{ averageRating }}</strong></div>
          <div><span>数据更新</span><strong class="summary-time">{{ formatTime(lastCrawl) || '-' }}</strong></div>
        </div>
      </section>

      <nav class="day-navigation" aria-label="比赛日筛选">
        <span class="day-nav-label">比赛日</span>
        <div class="day-scroll">
          <router-link :to="`/${cup}/`" class="day-chip" :class="{ active: !day }">
            <span>ALL</span>赛季总览
          </router-link>
          <router-link
            v-for="(d, index) in cupDays"
            :key="d"
            :to="`/${cup}/${d}/`"
            class="day-chip"
            :class="{ active: d === day }"
          ><span>{{ pad(index + 1) }}</span>{{ d }}</router-link>
        </div>
      </nav>

      <section class="leaderboard-section">
        <div class="section-heading public-heading leaderboard-heading">
          <h2>选手榜单</h2>
          <p>{{ day ? '数据按当日表现计算' : '数据按综合 Rating 默认排序；社区票选满 5 票后按加权均分显示' }}</p>
        </div>

        <div class="leaderboard-panel">
          <div class="data-toolbar public-toolbar">
            <label class="search-field" for="season-player-search">
              <AppIcon name="search" /><input id="season-player-search" v-model="query" type="search" placeholder="搜索选手或队伍">
            </label>
            <label class="select-field compact" for="season-sort">
              <AppIcon name="filter" />
              <select id="season-sort" v-model="sortKey">
                <option value="avg_pw_rating">按 Rating</option>
                <option value="kd_ratio">按 K/D</option>
                <option value="win_rate">按胜率</option>
                <option value="avg_adpr">按 ADPR</option>
                <option value="total_mvp">按 MVP</option>
                <option v-if="!day" value="community_rating">按社区票选</option>
              </select>
            </label>
            <span class="toolbar-summary">{{ filteredPlayers.length }} 名选手</span>
          </div>

          <div v-if="loading" class="loading-state leaderboard-loading" aria-live="polite"><span class="loader"></span><p>正在读取赛季数据…</p></div>
          <div v-else-if="error" class="empty-state public-empty" role="alert">
            <span><AppIcon name="alert" :size="25" /></span><h3>无法读取榜单</h3><p>{{ error }}</p>
            <button class="button subtle" type="button" @click="load">重新加载</button>
          </div>
          <div v-else-if="filteredPlayers.length" class="leaderboard-results">
            <div class="table-scroll leaderboard-scroll">
              <table class="data-table leaderboard-table">
              <thead>
                <tr>
                  <th class="rank-cell">排名</th><th>选手</th><th>完美段位</th><th v-if="day">称号</th><th>荣誉</th>
                  <th>场次</th><th>胜率</th><th>K/D</th><th>Rating</th>
                  <th class="draft-pick-heading" title="选人轮次与全场顺位；队长身份不计入平均">选马顺位</th>
                  <th v-if="!day" title="满 5 票后，使用向本赛季社区均值收缩的加权均分">
                    <span class="community-column-heading">
                      <span>社区票选</span>
                      <router-link
                        class="community-shelf-link"
                        :to="`/${cup}/community`"
                        aria-label="查看社区票选排名"
                        title="查看票选排名"
                      ><AppIcon name="layers" :size="15" /></router-link>
                    </span>
                  </th>
                  <th>ADPR</th><th>WE</th><th>爆头率</th><th>MVP</th><th class="action-cell"><span class="sr-only">查看详情</span></th>
                </tr>
              </thead>
              <tbody>
                <template v-for="(p, index) in filteredPlayers" :key="p.player_id">
                  <tr :class="{ expanded: open === p.player_id }">
                    <td class="rank-cell"><span class="rank-number" :class="{ top: index < 3 }">{{ pad(index + 1) }}</span></td>
                    <td>
                      <div class="identity-cell public-player">
                        <span class="live-room-slot">
                          <a
                            v-if="p.live_url"
                            class="live-room-link"
                            :class="`is-${p.live_status || 'checking'}`"
                            :href="p.live_url"
                            target="_blank"
                            rel="noopener noreferrer"
                            :aria-label="liveRoomLabel(p)"
                            :title="liveRoomTitle(p)"
                          ><AppIcon name="television" :size="14" /></a>
                        </span>
                        <PlayerAvatar :src="p.avatar" :name="displayName(p)" class="player-avatar" />
                        <span>
                          <router-link class="player-name-link" :to="playerLink(p)" :aria-label="`查看 ${displayName(p)} 的完整详情`">
                            {{ displayName(p) }}
                          </router-link>
                          <small>{{ p.team_name || p.nickname || '-' }}</small>
                        </span>
                      </div>
                    </td>
                    <td class="perfect-rank-cell">
                      <PerfectRankBadge
                        v-if="p.perfect_level"
                        :level="p.perfect_level"
                        :score="p.perfect_score"
                        :stars="p.perfect_stars"
                        :updated-at="p.perfect_rank_updated_at"
                        compact
                      />
                      <span v-else class="muted-cell">待更新</span>
                    </td>
                    <td v-if="day">
                      <div class="title-container">
                        <span
                          v-for="t in uniqueTitles(p.titles).slice(0, 2)"
                          :key="t.title_name"
                          class="title-badge"
                          :class="`title-${t.title_type}`"
                          :title="t.title_description"
                        >{{ t.title_name }}</span>
                        <span v-if="uniqueTitles(p.titles).length > 2" class="title-more">+{{ uniqueTitles(p.titles).length - 2 }}</span>
                        <span v-if="!uniqueTitles(p.titles).length" class="muted-cell">-</span>
                      </div>
                    </td>
                    <td><div class="trophy-container"><span v-for="(item, ti) in p.trophy_history || []" :key="ti" :class="item.trophy">{{ item.trophy === 'champion' ? '冠' : '亚' }}</span><span v-if="!p.trophy_history?.length">-</span></div></td>
                    <td class="mono-data">{{ p.match_count || 0 }}</td>
                    <td><span :class="{ 'stat-positive': p.win_rate >= 0.6 }">{{ pct(p.win_rate) }}</span></td>
                    <td class="mono-data">{{ n2(p.kd_ratio) }}</td>
                    <td><strong class="rating-value" :class="{ hot: p.avg_pw_rating >= 1.57 }">{{ n2(p.avg_pw_rating) }}</strong></td>
                    <td class="draft-pick-cell">
                      <span
                        v-if="hasDraftPick(p)"
                        class="draft-pick-value"
                        :title="draftPickTitle(p)"
                        :aria-label="draftPickTitle(p)"
                        tabindex="0"
                      >
                        <span><AppIcon name="layers" :size="14" /><strong>{{ draftRoundCompact(p) }}</strong></span>
                        <span><AppIcon name="users" :size="14" /><strong>≈{{ draftOverallPickNumber(p) }}</strong></span>
                      </span>
                      <span v-else class="muted-cell" aria-label="暂无被选记录">-</span>
                    </td>
                    <td
                      v-if="!day"
                      class="quick-vote-cell"
                      @mouseenter="openQuickVote(p, $event)"
                      @mouseleave="scheduleQuickVoteClose"
                    >
                      <button
                        class="quick-vote-trigger"
                        type="button"
                        :aria-label="`快速评价 ${displayName(p)} 的本赛季表现`"
                        aria-controls="season-quick-vote"
                        :aria-expanded="quickVotePlayer?.player_id === p.player_id"
                        @focus="openQuickVote(p, $event)"
                        @click="openQuickVote(p, $event)"
                      >
                        <span class="community-verdict" :class="{ formed: communityRatingReady(p) }">
                          <template v-if="communityRatingReady(p)">
                            <strong>{{ p.community_rating.label }}</strong>
                            <span>加权 {{ n2(p.community_rating.score) }} · {{ p.community_rating.total_votes }} 票</span>
                          </template>
                          <template v-else>
                            <span>{{ communityRatingCount(p) ? '样本积累中' : '暂无投票' }}</span>
                            <small v-if="communityRatingCount(p)">{{ communityRatingCount(p) }}/{{ p.community_rating?.minimum_votes || 5 }} 票</small>
                          </template>
                        </span>
                        <span class="quick-vote-cue" aria-hidden="true">快投<AppIcon name="target" :size="13" /></span>
                      </button>
                    </td>
                    <td class="mono-data">{{ n2(p.avg_adpr) }}</td>
                    <td class="mono-data">{{ n2(p.avg_we) }}</td>
                    <td class="mono-data">{{ pct(p.avg_headshot_ratio) }}</td>
                    <td class="mono-data">{{ p.total_mvp || 0 }}</td>
                    <td class="action-cell">
                      <div class="row-actions">
                        <button
                          class="icon-button compare-row-toggle"
                          :class="{ selected: compareIncludes(p.player_id) }"
                          type="button"
                          :aria-label="`${compareIncludes(p.player_id) ? '从对比中移除' : '加入对比'} ${displayName(p)}`"
                          :aria-pressed="compareIncludes(p.player_id)"
                          :title="compareIncludes(p.player_id) ? '移出对比' : '加入对比'"
                          @click="toggleCompare(p)"
                        ><AppIcon :name="compareIncludes(p.player_id) ? 'check' : 'plus'" /></button>
                        <button
                          class="icon-button"
                          type="button"
                          :aria-label="`${open === p.player_id ? '收起' : '展开'} ${displayName(p)} 的快速数据`"
                          :aria-expanded="open === p.player_id"
                          @click="togglePlayer(p.player_id)"
                        ><AppIcon name="chevronDown" :class="{ rotated: open === p.player_id }" /></button>
                        <router-link class="icon-button primary-icon" :to="playerLink(p)" :aria-label="`查看 ${displayName(p)} 的完整详情`" title="完整详情">
                          <AppIcon name="arrowRight" />
                        </router-link>
                      </div>
                    </td>
                  </tr>
                  <tr v-if="open === p.player_id" class="detail-drawer">
                    <td :colspan="15">
                      <div class="drawer-content">
                        <div v-if="uniqueTitles(p.titles).length" class="drawer-section titles-drawer">
                          <h3>称号信息</h3>
                          <div class="titles-grid">
                            <div v-for="t in uniqueTitles(p.titles)" :key="t.title_name" class="title-card" :class="`title-${t.title_type}`">
                              <strong>{{ t.title_name }}</strong><p>{{ t.title_description }}</p>
                            </div>
                          </div>
                        </div>
                        <div class="drawer-section">
                          <h3>基础数据</h3>
                          <dl class="quick-stat-grid">
                            <div><dt>胜场</dt><dd>{{ p.win_count || 0 }}</dd></div>
                            <div><dt>首杀 / 首死</dt><dd>{{ p.total_first_kills || 0 }} / {{ p.total_first_deaths || 0 }}</dd></div>
                            <div><dt>2K / 3K / 4K / 5K</dt><dd>{{ p.total_2k || 0 }} / {{ p.total_3k || 0 }} / {{ p.total_4k || 0 }} / {{ p.total_5k || 0 }}</dd></div>
                            <div><dt>1v2 / 1v3 / 1v4 / 1v5</dt><dd>{{ p.total_1v2 || 0 }} / {{ p.total_1v3 || 0 }} / {{ p.total_1v4 || 0 }} / {{ p.total_1v5 || 0 }}</dd></div>
                          </dl>
                        </div>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
              </table>
            </div>

            <ol class="mobile-leaderboard" aria-label="选手榜单">
              <li
                v-for="(p, index) in filteredPlayers"
                :key="`mobile-${p.player_id}`"
                class="mobile-player-card"
                :class="{ expanded: open === p.player_id }"
              >
                <div class="mobile-player-main">
                  <span class="rank-number" :class="{ top: index < 3 }" :aria-label="`第 ${index + 1} 名`">{{ pad(index + 1) }}</span>
                  <span class="live-room-slot">
                    <a
                      v-if="p.live_url"
                      class="live-room-link"
                      :class="`is-${p.live_status || 'checking'}`"
                      :href="p.live_url"
                      target="_blank"
                      rel="noopener noreferrer"
                      :aria-label="liveRoomLabel(p)"
                      :title="liveRoomTitle(p)"
                    ><AppIcon name="television" :size="14" /></a>
                  </span>
                  <PlayerAvatar :src="p.avatar" :name="displayName(p)" class="player-avatar" />
                  <div class="mobile-player-identity">
                    <router-link class="player-name-link" :to="playerLink(p)" :aria-label="`查看 ${displayName(p)} 的完整详情`">
                      {{ displayName(p) }}
                      <AppIcon name="arrowRight" :size="14" aria-hidden="true" />
                    </router-link>
                    <small>{{ p.team_name || p.nickname || '暂无队伍' }}</small>
                  </div>
                  <div class="mobile-rating">
                    <span>Rating</span>
                    <strong :class="{ hot: p.avg_pw_rating >= 1.57 }">{{ n2(p.avg_pw_rating) }}</strong>
                  </div>
                </div>

                <button
                  v-if="!day"
                  class="mobile-community-verdict quick-vote-mobile-trigger"
                  :class="{ formed: communityRatingReady(p) }"
                  type="button"
                  :aria-label="`快速评价 ${displayName(p)} 的本赛季表现`"
                  aria-controls="season-quick-vote"
                  :aria-expanded="quickVotePlayer?.player_id === p.player_id"
                  @click="openQuickVote(p, $event)"
                  @focus="openQuickVote(p, $event)"
                >
                  <span>社区票选</span>
                  <template v-if="communityRatingReady(p)">
                    <strong>{{ p.community_rating.label }}</strong>
                    <small>加权 {{ n2(p.community_rating.score) }} · {{ p.community_rating.total_votes }} 票</small>
                  </template>
                  <template v-else>
                    <strong>{{ communityRatingCount(p) ? '样本积累中' : '等待首票' }}</strong>
                    <small v-if="communityRatingCount(p)">{{ communityRatingCount(p) }}/{{ p.community_rating?.minimum_votes || 5 }} 票</small>
                  </template>
                  <AppIcon name="chevronDown" :size="14" aria-hidden="true" />
                </button>

                <div
                  v-if="hasDraftPick(p)"
                  class="mobile-draft-summary draft-pick-value"
                  :title="draftPickTitle(p)"
                  :aria-label="draftPickTitle(p)"
                  tabindex="0"
                >
                  <span><AppIcon name="layers" :size="14" /><strong>{{ draftRoundCompact(p) }}</strong></span>
                  <span><AppIcon name="users" :size="14" /><strong>≈{{ draftOverallPickNumber(p) }}</strong></span>
                </div>

                <dl class="mobile-key-stats">
                  <div><dt>K/D</dt><dd>{{ n2(p.kd_ratio) }}</dd></div>
                  <div><dt>胜率</dt><dd :class="{ 'stat-positive': p.win_rate >= 0.6 }">{{ pct(p.win_rate) }}</dd></div>
                  <div><dt>场次</dt><dd>{{ p.match_count || 0 }}</dd></div>
                  <div><dt>MVP</dt><dd>{{ p.total_mvp || 0 }}</dd></div>
                </dl>

                <div v-if="open === p.player_id" class="mobile-extra-stats">
                  <dl>
                    <div><dt>ADPR</dt><dd>{{ n2(p.avg_adpr) }}</dd></div>
                    <div><dt>WE</dt><dd>{{ n2(p.avg_we) }}</dd></div>
                    <div><dt>爆头率</dt><dd>{{ pct(p.avg_headshot_ratio) }}</dd></div>
                    <div><dt>胜场</dt><dd>{{ p.win_count || 0 }}</dd></div>
                  </dl>
                  <div v-if="p.perfect_level" class="mobile-perfect-rank">
                    <span>完美段位</span>
                    <PerfectRankBadge
                      :level="p.perfect_level"
                      :score="p.perfect_score"
                      :stars="p.perfect_stars"
                      :updated-at="p.perfect_rank_updated_at"
                      compact
                    />
                  </div>
                  <router-link class="mobile-detail-link" :to="playerLink(p)">
                    查看完整详情<AppIcon name="arrowRight" :size="15" />
                  </router-link>
                </div>

                <button
                  class="mobile-compare-button"
                  :class="{ selected: compareIncludes(p.player_id) }"
                  type="button"
                  :aria-pressed="compareIncludes(p.player_id)"
                  @click="toggleCompare(p)"
                >
                  <AppIcon :name="compareIncludes(p.player_id) ? 'check' : 'plus'" :size="15" />
                  {{ compareIncludes(p.player_id) ? '已加入对比' : '加入对比' }}
                </button>

                <button
                  class="mobile-expand-button"
                  type="button"
                  :aria-label="`${open === p.player_id ? '收起' : '展开'} ${displayName(p)} 的更多数据`"
                  :aria-expanded="open === p.player_id"
                  @click="togglePlayer(p.player_id)"
                >
                  {{ open === p.player_id ? '收起' : '更多数据' }}
                  <AppIcon name="chevronDown" :size="15" :class="{ rotated: open === p.player_id }" />
                </button>
              </li>
            </ol>
          </div>
          <div v-else class="empty-state public-empty">
            <span><AppIcon name="users" :size="25" /></span><h3>没有匹配的选手</h3><p>调整搜索条件，或切换其他比赛日。</p>
          </div>
        </div>
      </section>
    </main>
    <footer class="public-footer"><router-link to="/">返回全部赛季</router-link><span>{{ cupAlias || cup }} · 熊掌CS Major · Made with 🩷 By ZUOAJ</span></footer>
    <CompareTray :cup="String(cup || '')" :day="String(day || '')" />

    <Teleport to="body">
      <section
        v-if="quickVotePlayer"
        id="season-quick-vote"
        ref="quickVotePopoverEl"
        class="season-quick-vote"
        :style="quickVotePosition"
        role="dialog"
        :aria-label="`快速评价 ${displayName(quickVotePlayer)}`"
        @mouseenter="cancelQuickVoteClose"
        @mouseleave="scheduleQuickVoteClose"
        @focusin="cancelQuickVoteClose"
        @focusout="handleQuickVoteFocusOut"
        @keydown.esc.stop="closeQuickVote(true)"
      >
        <header class="season-quick-vote-heading">
          <div><span>QUICK VOTE</span><strong>{{ displayName(quickVotePlayer) }}</strong></div>
          <button type="button" aria-label="关闭快速投票" @click="closeQuickVote(true)"><AppIcon name="x" :size="16" /></button>
        </header>
        <p class="season-quick-vote-question">这赛季，你给什么档？</p>
        <div class="season-quick-vote-options" :aria-busy="quickVoteSubmitting">
          <button
            v-for="option in quickVoteOptions"
            :key="option.score"
            type="button"
            :class="{ selected: quickVoteData?.viewer_score === option.score }"
            :disabled="quickVoteSubmitting"
            :aria-label="`${option.label}：${option.hint}`"
            :title="option.hint"
            @click="submitQuickVote(option.score)"
          >
            <span>0{{ option.score }}</span><strong>{{ option.label }}</strong>
          </button>
        </div>
        <p v-if="quickVoteError" class="season-quick-vote-status error" role="alert"><AppIcon name="alert" :size="14" />{{ quickVoteError }}</p>
        <p v-else-if="quickVoteSubmitting" class="season-quick-vote-status">正在记录你的选择…</p>
        <p v-else-if="quickVoteData?.voted_today" class="season-quick-vote-status success"><AppIcon name="check" :size="14" />今日已投{{ selectedQuickVoteLabel }}，今天内可改</p>
        <p v-else-if="quickVoteLoading" class="season-quick-vote-status">正在读取今日投票状态…</p>
        <p v-else class="season-quick-vote-status">每天一票，当天可改</p>
      </section>
    </Teleport>
    <p class="sr-only" aria-live="polite">{{ quickVoteAnnouncement }} {{ compareAnnouncement }}</p>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import AppIcon from '../components/AppIcon.vue'
import CompareTray from '../components/CompareTray.vue'
import PlayerAvatar from '../components/PlayerAvatar.vue'
import PerfectRankBadge from '../components/PerfectRankBadge.vue'
import { addComparedPlayer, hydrateComparedPlayers, isPlayerCompared, removeComparedPlayer } from '../playerCompare'

const route = useRoute()
const cup = computed(() => route.params.cup)
const day = computed(() => route.params.day || '')
const cupAlias = ref('')
const players = ref([])
const cupDays = ref([])
const lastCrawl = ref('')
const error = ref('')
const loading = ref(true)
const open = ref('')
const query = ref('')
const sortKey = ref('avg_pw_rating')
const quickVotePlayer = ref(null)
const quickVoteData = ref(null)
const quickVoteLoading = ref(false)
const quickVoteSubmitting = ref(false)
const quickVoteError = ref('')
const quickVoteAnnouncement = ref('')
const compareAnnouncement = ref('')
const quickVotePopoverEl = ref(null)
const quickVotePosition = ref({ top: '0px', left: '0px', visibility: 'hidden' })

const defaultQuickVoteOptions = [
  { score: 5, label: '夯', hint: '统治级，没得说' },
  { score: 4, label: '顶级', hint: '大腿表现，很硬' },
  { score: 3, label: '人上人', hint: '高于平均，有说法' },
  { score: 2, label: 'NPC', hint: '中规中矩，正常发挥' },
  { score: 1, label: '拉完了', hint: '这季状态不在线' },
]
const quickVoteCache = new Map()
let quickVoteAnchor = null
let quickVoteCloseTimer = 0
let quickVoteSwitchTimer = 0
let quickVoteRequest = 0
let liveStatusTimer = 0

const filteredPlayers = computed(() => {
  const search = query.value.trim().toLowerCase()
  return players.value
    .filter((p) => !search || `${displayName(p)} ${p.nickname || ''} ${p.team_name || ''}`.toLowerCase().includes(search))
    .slice()
    .sort((a, b) => playerSortValue(b) - playerSortValue(a))
})
const topRating = computed(() => players.value.length ? n2(Math.max(...players.value.map((p) => Number(p.avg_pw_rating || 0)))) : '0.00')
const averageRating = computed(() => players.value.length ? n2(players.value.reduce((sum, p) => sum + Number(p.avg_pw_rating || 0), 0) / players.value.length) : '0.00')
const quickVoteOptions = computed(() => quickVoteData.value?.options || defaultQuickVoteOptions)
const selectedQuickVoteLabel = computed(() => quickVoteOptions.value.find(
  (option) => option.score === quickVoteData.value?.viewer_score,
)?.label || '')

function displayName(p) { return p.alias_name || p.nickname || p.player_id }
function n2(value) { return Number(value || 0).toFixed(2) }
function pct(value) { return `${(Number(value || 0) * 100).toFixed(1)}%` }
function pad(value) { return String(value || 0).padStart(2, '0') }
function formatTime(value) { return value ? String(value).replace('T', ' ').slice(0, 16) : '' }
function playerLink(p) { return `/player/${p.player_id}/${cup.value}${day.value ? `/${day.value}` : ''}/` }
function liveRoomState(p) { return p.live_status || 'checking' }
function liveRoomTitle(p) {
  const state = liveRoomState(p)
  if (state === 'live') return '正在直播，点击进入直播间'
  if (state === 'offline') return '当前未开播，点击进入直播间'
  if (state === 'unknown') return '暂时无法检测开播状态，点击进入直播间'
  return '正在检测开播状态'
}
function liveRoomLabel(p) { return `${displayName(p)}：${liveRoomTitle(p)}` }
function communityRatingReady(p) { return p.community_rating?.status === 'formed' }
function communityRatingCount(p) { return Number(p.community_rating?.total_votes || 0) }
function hasDraftPick(p) { return Number(p.draft_pick?.pick_count || 0) > 0 }
function draftRoundLabel(p) {
  const average = Number(p.draft_pick?.average_round || 0)
  const earlier = Math.floor(average)
  const later = Math.ceil(average)
  return earlier === later ? `第 ${earlier} 轮` : `第 ${earlier} 至 ${later} 轮间`
}
function draftRoundCompact(p) {
  const average = Number(p.draft_pick?.average_round || 0)
  const earlier = Math.floor(average)
  const later = Math.ceil(average)
  return earlier === later ? String(earlier) : `${earlier}-${later}`
}
function draftOverallPickNumber(p) {
  const average = Number(p.draft_pick?.average_overall_pick || 0)
  return Math.max(1, Math.round(average))
}
function draftPickTitle(p) {
  if (!hasDraftPick(p)) return '暂无被选记录'
  const teamCounts = (p.draft_pick.team_counts || []).map(Number).filter(Boolean)
  const scale = teamCounts.length ? `${teamCounts.join('、')} 队选人` : '选人记录'
  return `涵盖${scale}；平均位置在${draftRoundLabel(p)}，全场顺位按同轮中点估算。队长身份不计入平均。`
}
function playerSortValue(p) {
  if (sortKey.value === 'community_rating') {
    return communityRatingReady(p) ? Number(p.community_rating.score) : -1
  }
  return Number(p[sortKey.value] || 0)
}
function togglePlayer(id) { open.value = open.value === id ? '' : id }
function compareIncludes(playerId) { return isPlayerCompared(cup.value, day.value, playerId) }
function toggleCompare(player) {
  if (compareIncludes(player.player_id)) {
    removeComparedPlayer(cup.value, day.value, player.player_id)
    compareAnnouncement.value = `已从对比中移除 ${displayName(player)}`
    return
  }
  const result = addComparedPlayer(cup.value, day.value, player)
  compareAnnouncement.value = result.ok
    ? `已将 ${displayName(player)} 加入对比`
    : '最多只能同时对比 4 名选手'
}
function cancelQuickVoteClose() {
  window.clearTimeout(quickVoteCloseTimer)
  window.clearTimeout(quickVoteSwitchTimer)
  quickVoteCloseTimer = 0
  quickVoteSwitchTimer = 0
}
function scheduleQuickVoteClose() {
  cancelQuickVoteClose()
  quickVoteCloseTimer = window.setTimeout(() => closeQuickVote(), 240)
}
function updateQuickVotePosition() {
  if (!quickVotePlayer.value || !quickVoteAnchor?.isConnected) return
  const rect = quickVoteAnchor.getBoundingClientRect()
  const edge = 8
  const gap = 6
  const width = Math.min(360, window.innerWidth - edge * 2)
  const height = quickVotePopoverEl.value?.offsetHeight || 174
  const clampLeft = (value) => Math.min(Math.max(edge, value), window.innerWidth - width - edge)
  const clampTop = (value) => Math.min(Math.max(edge, value), window.innerHeight - height - edge)
  const roomLeft = rect.left - edge
  const roomRight = window.innerWidth - rect.right - edge
  const canUseSide = window.innerWidth >= 720
  let left
  let top
  if (canUseSide && roomLeft >= width + gap) {
    left = rect.left - width - gap
    top = clampTop(rect.top + rect.height / 2 - height / 2)
  } else if (canUseSide && roomRight >= width + gap) {
    left = rect.right + gap
    top = clampTop(rect.top + rect.height / 2 - height / 2)
  } else {
    left = clampLeft(rect.left + rect.width / 2 - width / 2)
    top = rect.top >= height + gap + edge
      ? rect.top - height - gap
      : clampTop(rect.bottom + gap)
  }
  quickVotePosition.value = { top: `${Math.round(top)}px`, left: `${Math.round(left)}px`, visibility: 'visible' }
}
async function loadQuickVote(player) {
  const playerId = String(player.player_id)
  const cached = quickVoteCache.get(playerId)
  if (cached) {
    quickVoteData.value = cached
    return
  }
  const requestId = ++quickVoteRequest
  quickVoteLoading.value = true
  try {
    const data = await api.playerCommunityRating(playerId, cup.value)
    quickVoteCache.set(playerId, data)
    if (requestId === quickVoteRequest && String(quickVotePlayer.value?.player_id) === playerId) {
      quickVoteData.value = data
      await nextTick()
      updateQuickVotePosition()
    }
  } catch (e) {
    if (requestId === quickVoteRequest && String(quickVotePlayer.value?.player_id) === playerId) {
      quickVoteError.value = e.message || '今日投票状态暂时无法读取。'
    }
  } finally {
    if (requestId === quickVoteRequest) quickVoteLoading.value = false
  }
}
function showQuickVote(player, anchor) {
  const playerId = String(player.player_id)
  const changed = String(quickVotePlayer.value?.player_id || '') !== playerId
  quickVoteAnchor = anchor || quickVoteAnchor
  if (changed) {
    quickVoteRequest += 1
    quickVotePlayer.value = player
    quickVoteData.value = quickVoteCache.get(playerId) || null
    quickVoteLoading.value = false
    quickVoteSubmitting.value = false
    quickVoteError.value = ''
  }
  quickVotePosition.value = { ...quickVotePosition.value, visibility: 'hidden' }
  nextTick(() => {
    updateQuickVotePosition()
    if (!quickVoteCache.has(playerId) && !quickVoteLoading.value) loadQuickVote(player)
  })
}
function openQuickVote(player, event) {
  const playerId = String(player.player_id)
  const currentId = String(quickVotePlayer.value?.player_id || '')
  const anchor = event?.currentTarget || quickVoteAnchor
  const isPassingAnotherRow = event?.type === 'mouseenter' && currentId && currentId !== playerId
  cancelQuickVoteClose()
  if (isPassingAnotherRow) {
    quickVoteSwitchTimer = window.setTimeout(() => {
      if (anchor?.isConnected && anchor.matches(':hover')) showQuickVote(player, anchor)
    }, 260)
    return
  }
  showQuickVote(player, anchor)
}
function closeQuickVote(restoreFocus = false) {
  cancelQuickVoteClose()
  const anchor = quickVoteAnchor
  quickVoteRequest += 1
  quickVotePlayer.value = null
  quickVoteData.value = null
  quickVoteLoading.value = false
  quickVoteSubmitting.value = false
  quickVoteError.value = ''
  quickVoteAnchor = null
  if (restoreFocus && anchor?.isConnected) anchor.focus?.()
}
function handleQuickVoteFocusOut(event) {
  const next = event.relatedTarget
  if (next && (quickVotePopoverEl.value?.contains(next) || quickVoteAnchor?.contains?.(next))) return
  scheduleQuickVoteClose()
}
function updatePlayerCommunityRating(playerId, data) {
  const player = players.value.find((item) => String(item.player_id) === String(playerId))
  if (!player) return
  const consensus = data.consensus || {}
  player.community_rating = {
    status: consensus.status || 'collecting',
    score: consensus.score ?? null,
    raw_average: consensus.raw_average ?? null,
    label: consensus.label ?? null,
    label_method: consensus.label_method || 'raw_average',
    total_votes: Number(data.total_votes || 0),
    minimum_votes: Number(data.minimum_votes || 5),
    method: consensus.method || 'bayesian_average',
  }
}
async function submitQuickVote(score) {
  const player = quickVotePlayer.value
  if (!player || quickVoteSubmitting.value) return
  const playerId = String(player.player_id)
  quickVoteRequest += 1
  quickVoteLoading.value = false
  quickVoteSubmitting.value = true
  quickVoteError.value = ''
  try {
    const data = await api.ratePlayer(playerId, cup.value, score)
    quickVoteCache.set(playerId, data)
    updatePlayerCommunityRating(playerId, data)
    if (String(quickVotePlayer.value?.player_id) === playerId) quickVoteData.value = data
    const selected = data.options?.find((option) => option.score === data.viewer_score)
    quickVoteAnnouncement.value = `已给 ${displayName(player)} 投${selected?.label || ''}，今天内可修改。`
    await nextTick()
    updateQuickVotePosition()
  } catch (e) {
    if (String(quickVotePlayer.value?.player_id) === playerId) {
      quickVoteError.value = e.message || '投票没有提交成功，请稍后重试。'
    }
  } finally {
    if (String(quickVotePlayer.value?.player_id) === playerId) quickVoteSubmitting.value = false
  }
}
function handleQuickVoteViewportChange() {
  if (quickVotePlayer.value) updateQuickVotePosition()
}
function handleQuickVoteOutside(event) {
  if (!quickVotePlayer.value) return
  if (quickVotePopoverEl.value?.contains(event.target) || quickVoteAnchor?.contains?.(event.target)) return
  closeQuickVote()
}
function uniqueTitles(list) {
  const seen = new Set()
  return (list || []).filter((title) => {
    if (seen.has(title.title_name)) return false
    seen.add(title.title_name)
    return true
  })
}
async function load() {
  closeQuickVote()
  quickVoteCache.clear()
  error.value = ''
  loading.value = true
  open.value = ''
  try {
    const data = await api.cup(cup.value, day.value || null)
    cupAlias.value = data.cup_alias || data.cup
    players.value = data.players || []
    hydrateComparedPlayers(cup.value, day.value, players.value)
    loadLiveStatuses(players.value)
    // “赛季总览”在模板中单独置顶；比赛日统一按日期倒序展示。
    cupDays.value = [...new Set((data.cup_days || []).filter(Boolean))].sort().reverse()
    lastCrawl.value = data.last_crawl_time || ''
    document.title = `${cupAlias.value}${day.value ? ` · ${day.value}` : ''} · 熊掌CS Major`
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadLiveStatuses(list) {
  const playerIds = list.filter((player) => player.live_url).map((player) => player.player_id)
  if (!playerIds.length) return
  try {
    const data = await api.liveStatuses(playerIds)
    const statuses = data.statuses || {}
    for (const player of list) {
      if (!player.live_url) continue
      player.live_status = statuses[String(player.player_id)]?.status || 'unknown'
    }
  } catch {
    for (const player of list) {
      if (player.live_url) player.live_status = 'unknown'
    }
  }
}

onMounted(() => {
  load()
  liveStatusTimer = window.setInterval(() => loadLiveStatuses(players.value), 60_000)
  window.addEventListener('resize', handleQuickVoteViewportChange)
  window.addEventListener('scroll', handleQuickVoteViewportChange, true)
  document.addEventListener('pointerdown', handleQuickVoteOutside)
})
onBeforeUnmount(() => {
  cancelQuickVoteClose()
  window.clearInterval(liveStatusTimer)
  window.removeEventListener('resize', handleQuickVoteViewportChange)
  window.removeEventListener('scroll', handleQuickVoteViewportChange, true)
  document.removeEventListener('pointerdown', handleQuickVoteOutside)
})
watch(() => [route.params.cup, route.params.day], load)
</script>
