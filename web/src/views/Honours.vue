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
          <h1>{{ payload?.cup_alias || cup }}<span>荣誉展</span></h1>
          <p>不只给冠军留位置。这里记录银牌、首轮、手感曲线，以及服务器数据和群友印象之间那些很难解释的瞬间。</p>
          <div class="honours-hero-actions">
            <button class="button primary" type="button" @click="feedbackOpen = true"><AppIcon name="message" :size="16" />提名一个新奖项</button>
            <small>说说奖项叫什么、它表彰什么，水友的脑洞会进入管理后台。</small>
          </div>
        </div>
        <dl class="honours-summary" aria-label="荣誉展概览">
          <div>
            <dt>状态</dt>
            <dd><span class="signal-dot"></span>{{ statusCopy.label }}</dd>
            <small>{{ statusCopy.note }}</small>
          </div>
          <div><dt>已开奖</dt><dd>{{ payload?.available_award_count || 0 }}<small>/ 18 项</small></dd></div>
          <div><dt>入围样本</dt><dd>{{ payload?.eligible_player_count || 0 }}<small>名选手</small></dd></div>
          <div><dt>基础门槛</dt><dd>{{ payload?.minimum_matches || 0 }}<small>张地图</small></dd></div>
        </dl>
      </section>

      <nav v-if="groups.length" class="honours-catalogue" aria-label="荣誉分类">
        <a v-for="(group, index) in groups" :key="group.key" :href="`#category-${group.key}`">
          <span>{{ pad(index + 1) }}</span>{{ group.label }}<small>{{ group.awards.length }}</small>
        </a>
      </nav>

      <div v-if="loading" class="honours-loading" aria-live="polite" aria-label="正在读取赛季荣誉">
        <article v-for="index in 6" :key="index" class="honour-skeleton"><span></span><strong></strong><i></i></article>
      </div>
      <section v-else-if="error" class="panel empty-state public-empty" role="alert">
        <span><AppIcon name="alert" :size="25" /></span>
        <h2>荣誉展暂时没有开门</h2>
        <p>{{ error }}</p>
        <button class="button subtle" type="button" @click="load">重新加载</button>
      </section>
      <template v-else>
        <section
          v-for="(group, groupIndex) in groups"
          :id="`category-${group.key}`"
          :key="group.key"
          class="honour-category"
        >
          <header class="honour-category-heading">
            <span>{{ pad(groupIndex + 1) }}</span>
            <div><h2>{{ group.label }}</h2><p>{{ categoryNotes[group.key] }}</p></div>
          </header>
          <div class="honours-grid">
            <article
              v-for="award in group.awards"
              :id="honourAnchor(award.key)"
              :key="award.key"
              class="honour-card"
              :class="{ 'is-collecting': award.status !== 'ready' }"
            >
              <header class="honour-card-heading">
                <div>
                  <span>{{ awardCode(award) }}</span>
                  <h3>{{ award.title }}</h3>
                </div>
                <span class="honour-state">{{ award.status === 'ready' ? 'TOP 3' : '待开奖' }}</span>
              </header>
              <p class="honour-description">{{ award.description }}</p>

              <ol class="honour-podium" :aria-label="`${award.title}前三名`">
                <li
                  v-for="slot in podiumSlots(award.entries)"
                  :key="slot.position"
                  :class="`position-${slot.position}`"
                >
                  <template v-if="slot.entry">
                    <router-link
                      class="podium-player"
                      :to="`/player/${encodeURIComponent(slot.entry.player_id)}/${encodeURIComponent(cup)}/`"
                      :aria-label="`查看第 ${slot.position} 名 ${slot.entry.name} 的详情`"
                    >
                      <span class="podium-avatar">
                        <PlayerAvatar :src="slot.entry.avatar" :name="slot.entry.name" />
                        <b>{{ slot.position }}</b>
                      </span>
                      <strong>{{ slot.entry.name }}</strong>
                    </router-link>
                    <span class="podium-value">{{ slot.entry.display_value }}</span>
                    <small>{{ slot.entry.evidence }}<em v-if="slot.entry.tied">同值</em></small>
                  </template>
                  <template v-else>
                    <span class="podium-avatar empty"><AppIcon name="users" :size="20" /><b>{{ slot.position }}</b></span>
                    <strong>待开奖</strong>
                    <span class="podium-value">—</span>
                    <small>样本仍在积累</small>
                  </template>
                  <span class="podium-plinth" aria-hidden="true"></span>
                </li>
              </ol>

              <footer class="honour-card-footer">
                <details>
                  <summary>怎么算的</summary>
                  <p>{{ award.method }}</p>
                </details>
                <button
                  v-if="award.status === 'ready'"
                  class="button subtle small"
                  type="button"
                  :disabled="Boolean(exportingKey)"
                  @click="downloadAward(award)"
                >
                  <span v-if="exportingKey === award.key" class="button-spinner dark"></span>
                  <AppIcon v-else name="save" :size="15" />
                  {{ exportingKey === award.key ? '生成中' : '下载奖卡' }}
                </button>
              </footer>
            </article>
          </div>
        </section>
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
          <li v-for="slot in podiumSlots(exportAward.entries)" :key="slot.position" :class="`position-${slot.position}`">
            <span class="poster-avatar">
              <PlayerAvatar v-if="slot.entry" :src="slot.entry.avatar" :name="slot.entry.name" />
              <AppIcon v-else name="users" :size="28" />
              <b>{{ slot.position }}</b>
            </span>
            <strong>{{ slot.entry?.name || '待开奖' }}</strong>
            <span>{{ slot.entry?.display_value || '—' }}</span>
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
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import AppIcon from '../components/AppIcon.vue'
import FeedbackDialog from '../components/FeedbackDialog.vue'
import PlayerAvatar from '../components/PlayerAvatar.vue'
import {
  groupHonours,
  honourAnchor,
  honourFilename,
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

const categoryNotes = {
  podium: '奖杯附近，总有一些熟面孔。',
  schedule: '来都来了，赛程总得留下点东西。',
  form: '把这个赛季和他自己的过去摆在一起。',
  contrast: '数字、段位和群友评价各说各话。',
  match: '输赢之外，服务器还记住了这些习惯。',
  specialist: '技能点没乱加，只是加得很有方向。',
}

const groups = computed(() => groupHonours(payload.value?.categories, payload.value?.awards))
const statusCopy = computed(() => honourStatus(payload.value?.status))

function pad(value) { return String(value).padStart(2, '0') }
function awardCode(award) {
  const index = (payload.value?.awards || []).findIndex((item) => item.key === award.key)
  return `HONOUR ${pad(index + 1)}`
}

async function scrollToHash() {
  if (!route.hash) return
  await nextTick()
  document.getElementById(route.hash.slice(1))?.scrollIntoView({ block: 'start' })
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
onMounted(load)
</script>
