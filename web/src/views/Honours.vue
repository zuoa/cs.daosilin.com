<template>
  <div class="public-site honours-page">
    <header class="public-nav compact-nav">
      <router-link class="public-brand" to="/" aria-label="返回数据首页">
        <span class="brand-mark"><AppIcon name="target" :size="22" /></span>
        <span><strong>熊掌CS Major</strong><small>COMPETITIVE ARCHIVE</small></span>
      </router-link>
      <nav aria-label="荣誉展页面导航">
        <router-link :to="`/${cup}/`"><AppIcon name="arrowLeft" />赛季数据</router-link>
      </nav>
    </header>

    <main class="honours-main">
      <section class="honours-hero">
        <div class="honours-title-block">
          <p class="section-kicker">SEASON HONOURS · {{ payload?.status === 'final' ? 'FINAL' : 'LIVE' }}</p>
          <h1><span class="honours-season-name">{{ payload?.cup_alias || cup }}</span><span class="honours-title-line">星光荣誉展</span></h1>
          <p>冠军只是其中一束光。银牌、手感曲线、奇怪搭档，以及服务器没忘掉的每一种名场面，都在这里轮流登台。</p>
          <div class="honours-hero-actions">
            <button class="button primary" type="button" @click="feedbackOpen = true"><AppIcon name="message" :size="16" />提名新奖项</button>
            <small>先说这个奖想表彰什么，公式可以之后再想。</small>
          </div>
        </div>
        <dl class="honours-summary" aria-label="荣誉展概览">
          <div><dt>状态</dt><dd><span class="signal-dot"></span>{{ statusCopy.label }}</dd><small>{{ statusCopy.note }}</small></div>
          <div><dt>已开奖</dt><dd>{{ payload?.available_award_count || 0 }}<small>/ {{ awards.length }} 项</small></dd></div>
          <div><dt>入围样本</dt><dd>{{ payload?.eligible_player_count || 0 }}<small>名选手</small></dd></div>
          <div><dt>组合门槛</dt><dd>{{ payload?.minimum_pair_maps || 0 }}<small>张同队地图</small></dd></div>
        </dl>
      </section>

      <section v-if="groups.length" class="honours-command" aria-label="荣誉展浏览方式">
        <div class="honours-view-switch" role="group" aria-label="切换荣誉展模式">
          <button type="button" :aria-pressed="viewMode === 'carousel'" @click="setViewMode('carousel')"><AppIcon name="television" :size="16" />逐项轮播</button>
          <button type="button" :aria-pressed="viewMode === 'overview'" @click="setViewMode('overview')"><AppIcon name="layers" :size="16" />一览全部</button>
        </div>
        <button
          v-if="viewMode === 'carousel'"
          class="honours-autoplay"
          type="button"
          :aria-pressed="isPaused"
          @click="toggleAutoplay"
        >
          <AppIcon :name="isPaused ? 'play' : 'pause'" :size="15" />
          {{ isPaused ? '继续轮播' : '暂停轮播' }}
        </button>
      </section>

      <div v-if="loading" class="honours-loading" aria-live="polite" aria-label="正在读取赛季荣誉">
        <article v-for="index in 3" :key="index" class="honour-skeleton"><span></span><strong></strong><i></i></article>
      </div>
      <section v-else-if="error" class="panel empty-state public-empty" role="alert">
        <span><AppIcon name="alert" :size="25" /></span>
        <h2>荣誉展暂时没有开门</h2>
        <p>{{ error }}</p>
        <button class="button subtle" type="button" @click="load">重新加载</button>
      </section>
      <template v-else-if="awards.length">
        <section
          v-if="viewMode === 'carousel'"
          ref="theatreEl"
          class="honours-theatre"
          aria-roledescription="轮播"
          aria-label="赛季荣誉逐项展览"
          @mouseenter="theatreHovered = true"
          @mouseleave="theatreHovered = false"
          @focusin="theatreFocused = true"
          @focusout="handleStageFocusOut"
        >
          <div class="honours-starfield" aria-hidden="true"><span></span><span></span><span></span></div>
          <div :key="activeAward.key" class="honours-fireworks" aria-hidden="true">
            <span></span><span></span><span></span>
          </div>
          <header class="honours-theatre-header">
            <div>
              <span>{{ activeGroup?.label }}</span>
              <p>{{ pad(activeIndex + 1) }} / {{ pad(awards.length) }}</p>
            </div>
            <nav aria-label="按分类跳转奖项">
              <button
                v-for="group in groups"
                :key="group.key"
                type="button"
                :aria-current="activeAward?.category === group.key ? 'true' : undefined"
                @click="jumpToGroup(group.key)"
              >{{ group.label }}</button>
            </nav>
          </header>

          <Transition :name="transitionDirection === 'next' ? 'honour-next' : 'honour-prev'" mode="out-in">
            <article
              :id="honourAnchor(activeAward.key)"
              :key="activeAward.key"
              class="honour-spotlight"
              :class="{ 'is-collecting': activeAward.status !== 'ready' }"
            >
              <header class="honour-spotlight-heading">
                <div>
                  <span>{{ awardCode(activeAward) }}</span>
                  <h2>{{ activeAward.title }}</h2>
                  <p>{{ activeAward.description }}</p>
                </div>
                <span class="honour-state">{{ awardStatusLabel(activeAward) }}</span>
              </header>

              <ol class="honour-podium spotlight-podium" :aria-label="`${activeAward.title}获奖名单`">
                <li v-for="slot in awardSlots(activeAward)" :key="slot.position" :class="`position-${slot.position}`">
                  <template v-if="slot.entry">
                    <div v-if="slot.entry.members?.length" class="podium-player podium-duo">
                      <span class="podium-duo-avatars">
                        <router-link
                          v-for="member in slot.entry.members"
                          :key="member.player_id"
                          class="podium-avatar"
                          :to="`/player/${encodeURIComponent(member.player_id)}/${encodeURIComponent(cup)}/`"
                          :aria-label="`查看 ${member.name} 的详情`"
                        ><PlayerAvatar :src="member.avatar" :name="member.name" /></router-link>
                        <b>{{ slot.position }}</b>
                      </span>
                      <strong>{{ slot.entry.name }}</strong>
                    </div>
                    <router-link
                      v-else
                      class="podium-player"
                      :to="`/player/${encodeURIComponent(slot.entry.player_id)}/${encodeURIComponent(cup)}/`"
                      :aria-label="`查看第 ${slot.position} 名 ${slot.entry.name} 的详情`"
                    >
                      <span class="podium-avatar"><PlayerAvatar :src="slot.entry.avatar" :name="slot.entry.name" /><b>{{ slot.position }}</b></span>
                      <strong>{{ slot.entry.name }}</strong>
                    </router-link>
                    <span class="podium-value">{{ slot.entry.display_value }}</span>
                    <small>{{ slot.entry.evidence }}<em v-if="slot.entry.tied">同值</em></small>
                  </template>
                  <template v-else>
                    <span class="podium-avatar empty"><AppIcon :name="activeAward.status === 'data_required' ? 'database' : 'users'" :size="21" /><b>{{ slot.position }}</b></span>
                    <strong>{{ activeAward.status === 'data_required' ? '等待阵营数据' : '待开奖' }}</strong>
                    <span class="podium-value">-</span>
                    <small>{{ activeAward.status === 'data_required' ? '不使用整图数据猜测 CT/T 表现' : '样本仍在积累' }}</small>
                  </template>
                  <span class="podium-plinth" aria-hidden="true"></span>
                </li>
              </ol>

              <footer class="honour-spotlight-footer">
                <div class="honours-progress" aria-hidden="true">
                  <span
                    v-if="!autoplayPaused"
                    :key="activeAward.key"
                    :style="{ '--autoplay-duration': `${autoplayDelay}ms` }"
                  ></span>
                </div>
                <div><span>计算口径</span><p>{{ activeAward.method }}</p></div>
                <button
                  v-if="activeAward.status === 'ready'"
                  class="button honour-download"
                  type="button"
                  :disabled="Boolean(exportingKey)"
                  @click="downloadAward(activeAward)"
                >
                  <span v-if="exportingKey === activeAward.key" class="button-spinner"></span>
                  <AppIcon v-else name="save" :size="15" />
                  {{ exportingKey === activeAward.key ? '生成中' : '下载奖卡' }}
                </button>
              </footer>
            </article>
          </Transition>

          <button class="honours-stage-arrow previous" type="button" aria-label="上一个奖项" @click="previousAward"><AppIcon name="arrowLeft" :size="22" /></button>
          <button class="honours-stage-arrow next" type="button" aria-label="下一个奖项" @click="nextAward"><AppIcon name="arrowRight" :size="22" /></button>
        </section>

        <div v-else class="honours-overview">
          <div class="honours-grid" aria-label="全部赛季荣誉">
            <article
              v-for="award in awards"
              :id="honourAnchor(award.key)"
              :key="award.key"
              class="honour-card"
              :class="{ 'is-collecting': award.status !== 'ready' }"
            >
                <header class="honour-card-heading"><div><span>{{ awardCode(award) }}</span><h3>{{ award.title }}</h3></div><span class="honour-state">{{ awardStatusLabel(award) }}</span></header>
                <p class="honour-description">{{ award.description }}</p>
                <ol class="honour-podium" :aria-label="`${award.title}获奖名单`">
                  <li v-for="slot in awardSlots(award)" :key="slot.position" :class="`position-${slot.position}`">
                    <template v-if="slot.entry">
                      <div v-if="slot.entry.members?.length" class="podium-player podium-duo">
                        <span class="podium-duo-avatars">
                          <router-link v-for="member in slot.entry.members" :key="member.player_id" class="podium-avatar" :to="`/player/${encodeURIComponent(member.player_id)}/${encodeURIComponent(cup)}/`" :aria-label="`查看 ${member.name} 的详情`"><PlayerAvatar :src="member.avatar" :name="member.name" /></router-link>
                          <b>{{ slot.position }}</b>
                        </span>
                        <strong>{{ slot.entry.name }}</strong>
                      </div>
                      <router-link v-else class="podium-player" :to="`/player/${encodeURIComponent(slot.entry.player_id)}/${encodeURIComponent(cup)}/`" :aria-label="`查看第 ${slot.position} 名 ${slot.entry.name} 的详情`">
                        <span class="podium-avatar"><PlayerAvatar :src="slot.entry.avatar" :name="slot.entry.name" /><b>{{ slot.position }}</b></span><strong>{{ slot.entry.name }}</strong>
                      </router-link>
                      <span class="podium-value">{{ slot.entry.display_value }}</span><small>{{ slot.entry.evidence }}<em v-if="slot.entry.tied">同值</em></small>
                    </template>
                    <template v-else>
                      <span class="podium-avatar empty"><AppIcon :name="award.status === 'data_required' ? 'database' : 'users'" :size="20" /><b>{{ slot.position }}</b></span>
                      <strong>{{ award.status === 'data_required' ? '等待阵营数据' : '待开奖' }}</strong><span class="podium-value">-</span><small>{{ award.status === 'data_required' ? '不猜测 CT/T 表现' : '样本仍在积累' }}</small>
                    </template>
                    <span class="podium-plinth" aria-hidden="true"></span>
                  </li>
                </ol>
                <footer class="honour-card-footer">
                  <details><summary>怎么算的</summary><p>{{ award.method }}</p></details>
                  <button v-if="award.status === 'ready'" class="button honour-download small" type="button" :disabled="Boolean(exportingKey)" @click="downloadAward(award)">
                    <span v-if="exportingKey === award.key" class="button-spinner"></span><AppIcon v-else name="save" :size="15" />{{ exportingKey === award.key ? '生成中' : '下载奖卡' }}
                  </button>
                </footer>
            </article>
          </div>
        </div>
        <p v-if="downloadError" class="honour-download-error" role="alert"><AppIcon name="alert" :size="15" />{{ downloadError }}</p>
      </template>
    </main>

    <footer class="public-footer">
      <router-link :to="`/${cup}/`">返回赛季数据</router-link>
      <span>{{ payload?.cup_alias || cup }} · 熊掌CS Major · Made with 🩷 By ZUOAJ</span>
    </footer>

    <div v-if="exportAward" class="honour-poster-render" aria-hidden="true">
    <article ref="posterEl" class="honour-poster">
      <header>
        <div class="honour-poster-brand"><span><AppIcon name="target" :size="27" /></span><strong>熊掌CS Major</strong></div>
        <p>{{ payload?.cup_alias || cup }} · SEASON HONOURS</p>
      </header>
      <section>
        <div class="honour-poster-copy">
          <span>{{ awardCode(exportAward) }}</span>
          <h2>{{ exportAward.title }}</h2>
          <p>{{ exportAward.description }}</p>
        </div>
        <ol class="honour-poster-podium">
          <li v-for="slot in awardSlots(exportAward)" :key="slot.position" :class="`position-${slot.position}`">
            <span v-if="slot.entry?.members?.length" class="poster-duo-avatars">
              <span v-for="member in slot.entry.members" :key="member.player_id" class="poster-avatar"><PlayerAvatar :src="member.avatar" :name="member.name" /></span>
              <b>{{ slot.position }}</b>
            </span>
            <span v-else class="poster-avatar">
              <PlayerAvatar v-if="slot.entry" :src="slot.entry.avatar" :name="slot.entry.name" />
              <AppIcon v-else name="users" :size="28" />
              <b>{{ slot.position }}</b>
            </span>
            <strong>{{ slot.entry?.name || '待开奖' }}</strong>
            <span>{{ slot.entry?.display_value || '-' }}</span>
            <small>{{ slot.entry?.evidence || '样本仍在积累' }}</small>
          </li>
        </ol>
      </section>
      <footer>
        <p>{{ exportAward.method }}</p>
        <div><span>扫码查看完整荣誉展</span><img v-if="posterQr" :src="posterQr" alt=""></div>
      </footer>
    </article>
    </div>
    <p class="sr-only" aria-live="polite">{{ announcement }}</p>
    <FeedbackDialog
      :open="feedbackOpen"
      type="award_suggestion"
      :context="{ type: 'season', id: cup, label: payload?.cup_alias || cup }"
      :copy="feedbackCopy"
      :detail-fields="feedbackDetails"
      @close="feedbackOpen = false"
      @submitted="announcement = '奖项提名已提交'"
    />
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import AppIcon from '../components/AppIcon.vue'
import FeedbackDialog from '../components/FeedbackDialog.vue'
import PlayerAvatar from '../components/PlayerAvatar.vue'
import {
  carouselIndex,
  groupHonours,
  honourAnchor,
  honourFilename,
  honourIndexByHash,
  honourSharePath,
  honourStatus,
  podiumSlots,
} from '../honours'

const route = useRoute()
const cup = computed(() => String(route.params.cup || ''))
const payload = ref(null)
const loading = ref(true)
const error = ref('')
const exportingKey = ref('')
const exportAward = ref(null)
const posterEl = ref(null)
const posterQr = ref('')
const downloadError = ref('')
const announcement = ref('')
const feedbackOpen = ref(false)
const viewMode = ref('carousel')
const activeIndex = ref(0)
const transitionDirection = ref('next')
const isPaused = ref(false)
const theatreHovered = ref(false)
const theatreFocused = ref(false)
const pageHidden = ref(false)
const theatreEl = ref(null)
const autoplayDelay = 7000
let autoplayTimer = null

const feedbackCopy = {
  eyebrow: 'COMMUNITY NOMINATION',
  title: '把新奖项写进候选名单',
  description: '不用先想好公式。先说清这个奖想表彰哪种名场面，我们会在后台查看并回复。',
  subjectLabel: '奖项名称',
  subjectPlaceholder: '例如：烟雾弹建筑师',
  contentLabel: '这个奖项表彰什么？',
  contentPlaceholder: '例如：奖励最会用烟雾弹切割战场、给队友创造空间的人。',
  contentHint: '请描述奖项的含义，避免只留下一个名字。',
  submitterLabel: '怎么称呼你（可选）',
  submitterPlaceholder: '群昵称或游戏 ID',
  submitLabel: '提交奖项提名',
  successTitle: '提名已进入候选名单',
  successDescription: '管理员可以在反馈收件箱查看并回复；下次打开这里就能看到处理进度。',
  historyTitle: '我的近期提名',
}
const feedbackDetails = [
  { key: 'method', label: '你觉得可以怎么算（可选）', placeholder: '可以写数据口径，也可以举一个具体例子。', maxlength: 500 },
]

const groups = computed(() => groupHonours(payload.value?.categories, payload.value?.awards))
const awards = computed(() => payload.value?.awards || [])
const activeAward = computed(() => awards.value[activeIndex.value] || null)
const activeGroup = computed(() => groups.value.find((group) => group.key === activeAward.value?.category))
const autoplayPaused = computed(() => (
  isPaused.value || theatreHovered.value || theatreFocused.value || pageHidden.value
  || viewMode.value !== 'carousel' || awards.value.length < 2
))
const statusCopy = computed(() => honourStatus(payload.value?.status))

function pad(value) { return String(value).padStart(2, '0') }
function awardCode(award) {
  const index = (payload.value?.awards || []).findIndex((item) => item.key === award.key)
  return `HONOUR ${pad(index + 1)}`
}

function awardStatusLabel(award) {
  if (award.is_manual) return `获奖 ${award.entries.length} 人`
  if (award.status === 'ready') return 'TOP 3'
  if (award.status === 'data_required') return '待补数据'
  return '待开奖'
}

function awardSlots(award) {
  if (award?.is_manual) {
    return (award.entries || []).map((entry, index) => ({
      position: Number(entry.position) || index + 1,
      entry,
    }))
  }
  return podiumSlots(award?.entries || [])
}

function syncAwardHash(award) {
  if (!award || typeof window === 'undefined') return
  const url = `${window.location.pathname}${window.location.search}#${honourAnchor(award.key)}`
  window.history.replaceState(window.history.state, '', url)
}

function setActiveAward(index, { announce = true, syncHash = true, direction = '' } = {}) {
  const nextIndex = carouselIndex(index, awards.value.length)
  transitionDirection.value = direction || (nextIndex < activeIndex.value ? 'prev' : 'next')
  activeIndex.value = nextIndex
  if (syncHash) syncAwardHash(activeAward.value)
  if (announce && activeAward.value) announcement.value = `正在展示：${activeAward.value.title}`
}

function nextAward() { setActiveAward(activeIndex.value + 1, { direction: 'next' }) }
function previousAward() { setActiveAward(activeIndex.value - 1, { direction: 'prev' }) }

function jumpToGroup(groupKey) {
  const index = awards.value.findIndex((award) => award.category === groupKey)
  if (index >= 0) setActiveAward(index)
}

async function setViewMode(mode) {
  viewMode.value = mode
  announcement.value = mode === 'carousel' ? '已切换到逐项轮播' : '已切换到一览全部'
  await nextTick()
  if (mode === 'overview' && route.hash) {
    document.getElementById(route.hash.slice(1))?.scrollIntoView({ block: 'start' })
  }
}

function toggleAutoplay() {
  isPaused.value = !isPaused.value
  announcement.value = isPaused.value ? '已暂停自动轮播' : '已继续自动轮播'
}

function handleStageFocusOut(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) theatreFocused.value = false
}

function scheduleAutoplay() {
  window.clearTimeout(autoplayTimer)
  autoplayTimer = null
  if (autoplayPaused.value) return
  autoplayTimer = window.setTimeout(() => {
    setActiveAward(activeIndex.value + 1, { announce: false, syncHash: false })
  }, autoplayDelay)
}

function handleVisibilityChange() {
  pageHidden.value = document.hidden
}

async function scrollToHash() {
  if (!route.hash) return
  await nextTick()
  activeIndex.value = honourIndexByHash(awards.value, route.hash)
  if (viewMode.value === 'overview') {
    document.getElementById(route.hash.slice(1))?.scrollIntoView({ block: 'start' })
  }
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    payload.value = await api.honours(cup.value)
  } catch (err) {
    error.value = err.message || '请稍后再试。'
  } finally {
    loading.value = false
  }
  if (!error.value) await scrollToHash()
}

async function waitForImages(root) {
  await Promise.all([...root.querySelectorAll('img')].map((image) => {
    if (image.complete) return image.decode?.().catch(() => {})
    return new Promise((resolve) => {
      image.addEventListener('load', resolve, { once: true })
      image.addEventListener('error', resolve, { once: true })
    })
  }))
}

async function downloadAward(award) {
  exportingKey.value = award.key
  downloadError.value = ''
  announcement.value = `正在生成${award.title}奖卡`
  try {
    const shareUrl = new URL(honourSharePath(cup.value, award.key), window.location.origin).href
    const [{ toDataURL }, { toPng }] = await Promise.all([import('qrcode'), import('html-to-image')])
    posterQr.value = await toDataURL(shareUrl, { width: 112, margin: 1 })
    exportAward.value = award
    await nextTick()
    await waitForImages(posterEl.value)
    const dataUrl = await toPng(posterEl.value, {
      width: 1200,
      height: 675,
      pixelRatio: 1,
      cacheBust: true,
    })
    const link = document.createElement('a')
    link.download = honourFilename(payload.value?.cup_alias || cup.value, award.title)
    link.href = dataUrl
    link.click()
    announcement.value = `${award.title}奖卡已下载`
  } catch (err) {
    downloadError.value = `“${award.title}”奖卡生成失败，请重试。`
    announcement.value = downloadError.value
  } finally {
    exportAward.value = null
    posterQr.value = ''
    exportingKey.value = ''
  }
}

watch(() => route.hash, scrollToHash)
watch(cup, load)
watch([activeIndex, autoplayPaused, () => awards.value.length], scheduleAutoplay)
onMounted(() => {
  isPaused.value = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches || false
  document.addEventListener('visibilitychange', handleVisibilityChange)
  load()
})
onBeforeUnmount(() => {
  window.clearTimeout(autoplayTimer)
  document.removeEventListener('visibilitychange', handleVisibilityChange)
})
</script>
