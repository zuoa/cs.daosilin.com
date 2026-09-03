<template>
  <div class="public-site community-shelves-page">
    <header class="public-nav compact-nav">
      <router-link class="public-brand" to="/" aria-label="返回数据首页">
        <span class="brand-mark"><AppIcon name="target" :size="22" /></span>
        <span><strong>熊掌CS Major</strong><small>COMPETITIVE ARCHIVE</small></span>
      </router-link>
      <nav aria-label="社区票选页面导航">
        <router-link :to="`/${cup}/`"><AppIcon name="arrowLeft" />返回选手榜单</router-link>
      </nav>
    </header>

    <main class="community-shelves-main">
      <section class="community-shelves-hero">
        <div>
          <h1><span>{{ cupAlias || cup }}</span><span>从夯到拉排名</span></h1>
          <p>按票选结果分层展示，满 5 票后正式上架。</p>
        </div>
        <dl class="community-shelves-summary" aria-label="票选排名概览">
          <div><dt>参评选手</dt><dd>{{ players.length }}</dd></div>
          <div><dt>已经成榜</dt><dd>{{ formedCount }}</dd></div>
          <div><dt>等待成榜</dt><dd>{{ pendingCount }}</dd></div>
        </dl>
      </section>

      <section class="community-shelf-board" aria-label="社区票选五档排名">
        <div v-if="loading" class="community-shelves-loading" aria-live="polite" aria-label="正在读取社区票选结果">
          <article v-for="tier in tiers" :key="tier.score" class="community-shelf-tier shelf-tier-skeleton">
            <header class="community-shelf-label">
              <span>{{ pad(tier.score) }}</span><AppIcon :name="tier.icon" :size="27" /><strong>{{ tier.label }}</strong>
            </header>
            <div class="community-shelf-runway">
              <div class="community-shelf-players" aria-hidden="true">
                <span v-for="index in 6" :key="index" class="shelf-player-skeleton"><i></i><b></b></span>
              </div>
            </div>
          </article>
        </div>

        <div v-else-if="error" class="empty-state community-shelves-error" role="alert">
          <span><AppIcon name="alert" :size="25" /></span>
          <h2>无法读取票选排名</h2>
          <p>{{ error }}</p>
          <button class="button subtle" type="button" @click="load">重新加载</button>
        </div>

        <div v-else class="community-shelves-list">
          <article v-for="tier in tiers" :key="tier.score" class="community-shelf-tier">
            <header class="community-shelf-label">
              <span>{{ pad(tier.score) }}</span>
              <AppIcon :name="tier.icon" :size="27" />
              <strong>{{ tier.label }}</strong>
              <small>{{ groupedPlayers[tier.label].length }} 名</small>
            </header>
            <div class="community-shelf-runway">
              <div v-if="groupedPlayers[tier.label].length" class="community-shelf-players">
                <router-link
                  v-for="player in groupedPlayers[tier.label]"
                  :key="player.player_id"
                  class="community-shelf-player"
                  :to="playerLink(player)"
                  :aria-label="`查看 ${displayName(player)} 的选手详情`"
                >
                  <PlayerAvatar :src="player.avatar" :name="displayName(player)" class="community-shelf-avatar" />
                  <strong>{{ displayName(player) }}</strong>
                </router-link>
              </div>
              <p v-else class="community-shelf-empty">暂无选手上架</p>
            </div>
          </article>
        </div>
      </section>
    </main>

    <footer class="public-footer">
      <router-link :to="`/${cup}/`">返回选手榜单</router-link>
      <span>{{ cupAlias || cup }} · 熊掌CS Major · Made with 🩷 By ZUOAJ</span>
    </footer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import AppIcon from '../components/AppIcon.vue'
import PlayerAvatar from '../components/PlayerAvatar.vue'

const tiers = [
  { score: 5, label: '夯', icon: 'tierHam' },
  { score: 4, label: '顶级', icon: 'tierElite' },
  { score: 3, label: '人上人', icon: 'tierUpper' },
  { score: 2, label: 'NPC', icon: 'tierNpc' },
  { score: 1, label: '拉完了', icon: 'tierBottom' },
]

const route = useRoute()
const cup = computed(() => String(route.params.cup || ''))
const cupAlias = ref('')
const players = ref([])
const loading = ref(true)
const error = ref('')

const groupedPlayers = computed(() => {
  const groups = Object.fromEntries(tiers.map((tier) => [tier.label, []]))
  for (const player of players.value) {
    const rating = player.community_rating
    if (rating?.status === 'formed' && groups[rating.label]) groups[rating.label].push(player)
  }
  for (const group of Object.values(groups)) {
    group.sort((a, b) => (
      Number(b.community_rating?.score || 0) - Number(a.community_rating?.score || 0)
      || Number(b.community_rating?.total_votes || 0) - Number(a.community_rating?.total_votes || 0)
      || displayName(a).localeCompare(displayName(b), 'zh-CN')
    ))
  }
  return groups
})

const formedCount = computed(() => Object.values(groupedPlayers.value).reduce((total, group) => total + group.length, 0))
const pendingCount = computed(() => Math.max(0, players.value.length - formedCount.value))

function displayName(player) {
  return player.alias_name || player.nickname || player.player_id
}

function pad(value) {
  return String(value).padStart(2, '0')
}

function playerLink(player) {
  return `/player/${player.player_id}/${cup.value}/`
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api.cup(cup.value)
    cupAlias.value = data.cup_alias || data.cup
    players.value = data.players || []
    document.title = `${cupAlias.value}从夯到拉排名 · 熊掌CS Major`
  } catch (e) {
    error.value = e.message || '票选结果暂时无法读取。'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(cup, load)
</script>

<style scoped>
.community-shelves-main {
  width: min(1420px, calc(100% - 64px));
  min-height: calc(100dvh - 152px);
  margin: 0 auto;
  padding: 34px 0 78px;
}

.community-shelves-hero {
  display: flex;
  min-height: 186px;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--space-xl);
  border-bottom: var(--rule-fine) solid var(--color-ink);
  padding: 20px 0 30px;
}

.community-shelves-hero h1 {
  margin-top: var(--space-2xs);
  font-family: var(--font-display);
  font-size: clamp(2.7rem, 5vw, 5rem);
  letter-spacing: -.055em;
  line-height: .95;
}

.community-shelves-hero > div > p:last-child {
  margin-top: var(--space-xs);
  color: var(--color-muted);
  font-size: var(--text-sm);
}

.community-shelves-summary {
  display: grid;
  min-width: min(520px, 46%);
  grid-template-columns: repeat(3, minmax(110px, 1fr));
  border: var(--rule-hair) solid var(--color-rule);
  background: var(--color-surface);
}

.community-shelves-summary > div {
  min-height: 82px;
  border-right: var(--rule-hair) solid var(--color-rule);
  padding: 15px 17px;
}

.community-shelves-summary > div:last-child { border-right: 0; }
.community-shelves-summary dt { color: var(--color-muted); font-size: .66rem; }
.community-shelves-summary dd {
  margin-top: 5px;
  font-family: var(--font-outlier);
  font-size: var(--text-xl);
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.community-shelf-board { margin-top: var(--space-xl); }
.community-shelves-list,
.community-shelves-loading { display: grid; gap: var(--space-sm); }

.community-shelf-tier {
  display: grid;
  min-width: 0;
  grid-template-columns: 172px minmax(0, 1fr);
  overflow: hidden;
  border: var(--rule-hair) solid var(--color-rule-2);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
  box-shadow: var(--shadow-card);
}

.community-shelf-label {
  display: grid;
  grid-template-columns: 35px minmax(0, 1fr);
  align-content: center;
  border-right: var(--rule-hair) solid var(--color-dark-rule);
  padding: 18px 20px;
  background: var(--color-ink);
  color: var(--color-dark-text);
}

.community-shelf-label span {
  grid-column: 1 / -1;
  color: var(--color-accent);
  font-family: var(--font-outlier);
  font-size: .65rem;
  font-weight: 800;
}

.community-shelf-label > svg {
  grid-column: 1;
  grid-row: 2 / 4;
  align-self: center;
  color: var(--color-accent);
}

.community-shelf-label strong {
  grid-column: 2;
  margin-top: 3px;
  font-family: var(--font-display);
  font-size: var(--text-xl);
  letter-spacing: -.035em;
  line-height: 1;
}

.community-shelf-label small {
  grid-column: 2;
  margin-top: 7px;
  color: var(--color-dark-muted);
  font-size: .64rem;
}

.community-shelf-runway {
  position: relative;
  min-width: 0;
  min-height: 132px;
  overflow: hidden;
  padding: 15px 20px 24px;
  background: var(--color-paper-2);
}

.community-shelf-runway::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 10px;
  background: var(--color-ink-2);
  box-shadow: 0 5px 0 var(--color-rule-2);
  content: "";
}

.community-shelf-players {
  display: flex;
  min-width: 0;
  flex-wrap: wrap;
  align-content: flex-start;
  gap: 14px;
  padding: 2px 2px 7px;
}

.community-shelf-player {
  display: grid;
  width: 82px;
  flex: 0 0 82px;
  justify-items: center;
  gap: 7px;
  color: var(--color-ink);
  text-align: center;
  transition: color var(--dur-short) var(--ease-out), transform var(--dur-short) var(--ease-out);
}

.community-shelf-player :deep(.community-shelf-avatar) {
  width: 68px;
  height: 68px;
  border: var(--rule-hair) solid var(--color-rule-2);
  border-radius: var(--radius-card);
  object-fit: cover;
  background: var(--color-surface);
  box-shadow: 0 3px 0 var(--color-rule);
}

.community-shelf-player :deep(.community-shelf-avatar.avatar-fallback) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--color-accent-soft);
  color: var(--color-accent-strong);
  font-family: var(--font-display);
  font-size: var(--text-lg);
  font-weight: 800;
}

.community-shelf-player strong {
  width: 100%;
  overflow: hidden;
  font-size: .72rem;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.community-shelf-player:hover { color: var(--color-accent-strong); transform: translateY(-2px); }
.community-shelf-player:focus-visible { border-radius: var(--radius-input); outline: 2px solid var(--color-focus); outline-offset: 3px; box-shadow: none; }

.community-shelf-empty {
  display: flex;
  min-height: 93px;
  align-items: center;
  color: var(--color-muted);
  font-size: var(--text-sm);
}

.community-shelves-error {
  min-height: 430px;
  border: var(--rule-hair) solid var(--color-rule);
  border-radius: var(--radius-panel);
  background: var(--color-surface);
}

.shelf-player-skeleton {
  display: grid;
  width: 82px;
  flex: 0 0 82px;
  justify-items: center;
  gap: 9px;
}

.shelf-player-skeleton i,
.shelf-player-skeleton b {
  display: block;
  border-radius: var(--radius-card);
  background: var(--gradient-skeleton);
  background-size: 200% 100%;
  animation: shelfSkeleton 1.5s var(--ease-in-out) infinite;
}

.shelf-player-skeleton i { width: 68px; height: 68px; }
.shelf-player-skeleton b { width: 58px; height: 10px; border-radius: 3px; }

@keyframes shelfSkeleton {
  50% { opacity: .45; background-position: 100% 0; }
}

@media (max-width: 61.25rem) {
  .community-shelves-hero { align-items: flex-start; flex-direction: column; }
  .community-shelves-summary { width: 100%; min-width: 0; }
}

@media (max-width: 45rem) {
  .community-shelves-main { width: calc(100% - 32px); padding: 18px 0 54px; }
  .community-shelves-hero { min-height: auto; gap: var(--space-lg); padding: 18px 0 24px; }
  .community-shelves-hero h1 { font-size: clamp(2.4rem, 12vw, 3.5rem); }
  .community-shelves-hero h1 > span:last-child { display: block; }
  .community-shelves-summary > div { min-height: 72px; padding: 12px 10px; }
  .community-shelves-summary dd { font-size: var(--text-lg); }
  .community-shelf-board { margin-top: var(--space-lg); }
  .community-shelves-list,
  .community-shelves-loading { gap: var(--space-xs); }
  .community-shelf-tier { grid-template-columns: minmax(0, 1fr); }
  .community-shelf-label {
    min-height: 56px;
    grid-template-columns: auto 28px minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    border-right: 0;
    padding: 12px 15px;
  }
  .community-shelf-label span { grid-column: 1; }
  .community-shelf-label > svg { grid-column: 2; grid-row: 1; }
  .community-shelf-label strong { grid-column: 3; }
  .community-shelf-label small { grid-column: 4; }
  .community-shelf-label strong { margin-top: 0; font-size: var(--text-lg); }
  .community-shelf-label small { margin-top: 0; }
  .community-shelf-runway { min-height: 122px; padding: 13px 13px 23px; }
  .community-shelf-players { gap: 9px; }
  .community-shelf-player,
  .shelf-player-skeleton { width: 74px; flex-basis: 74px; }
  .community-shelf-player :deep(.community-shelf-avatar),
  .shelf-player-skeleton i { width: 62px; height: 62px; }
  .community-shelf-empty { min-height: 86px; }
}

@media (prefers-reduced-motion: reduce) {
  .community-shelf-player { transition: none; }
  .community-shelf-player:hover { transform: none; }
  .shelf-player-skeleton i,
  .shelf-player-skeleton b { animation: none; }
}
</style>
