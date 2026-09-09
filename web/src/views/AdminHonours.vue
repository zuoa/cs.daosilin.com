<template>
  <AdminLayout title="荣誉奖项" description="为赛季补充无法只靠数据公式表达的特别奖项，并公开每位获奖者的入选理由。">
    <template #actions>
      <router-link v-if="cup" class="button subtle" :to="`/${cup}/honours`">
        <AppIcon name="external" />查看荣誉展
      </router-link>
    </template>

    <section class="panel honour-season-bar" aria-labelledby="honour-season-title">
      <div>
        <span class="honour-admin-mark"><AppIcon name="trophy" :size="22" /></span>
        <div><h2 id="honour-season-title">评审工作台</h2><p>自动榜单每天 03:00 生成快照；手动奖项保存后立即加入公开荣誉展。</p></div>
      </div>
      <label class="field-group honour-season-select">
        <span>当前赛季</span>
        <select v-model="cup" @change="changeSeason">
          <option value="">选择赛季</option>
          <option v-for="season in seasons" :key="season.cup_name" :value="season.cup_name">{{ displaySeason(season) }}</option>
        </select>
      </label>
      <div class="honour-snapshot">
        <span>自动榜单快照</span>
        <strong>{{ snapshotLabel }}</strong>
      </div>
    </section>

    <div v-if="loading" class="panel loading-state"><span class="loader"></span><p>读取奖项与参赛选手…</p></div>
    <div v-else-if="!cup" class="panel empty-state">
      <span><AppIcon name="trophy" :size="24" /></span><h3>先选择一个赛季</h3><p>选择后可以创建、编辑和删除该赛季的手动奖项。</p>
    </div>
    <div v-else class="honour-admin-grid">
      <section class="panel honour-composer" aria-labelledby="honour-composer-title">
        <div class="panel-header">
          <div><h2 id="honour-composer-title">{{ editingId ? '编辑奖项' : '添加奖项' }}</h2><p>{{ editingId ? '修改内容会立即同步到公开页。' : '奖项可以授予 1–3 名选手。' }}</p></div>
          <button v-if="editingId" class="button subtle small" type="button" @click="resetForm"><AppIcon name="x" />取消编辑</button>
        </div>

        <form class="honour-form" @submit.prevent="saveAward">
          <label class="field-group">
            <span>奖项名称</span>
            <input v-model.trim="form.title" maxlength="120" required placeholder="例如：关键局定心丸">
          </label>
          <label class="field-group">
            <span>奖项说明</span>
            <textarea v-model.trim="form.description" maxlength="1000" required placeholder="这个奖表彰什么，以及它为什么值得被记住。"></textarea>
          </label>

          <fieldset class="recipient-fieldset">
            <legend>获奖名单与理由</legend>
            <p>第一位必填，第二、三位可以留空；名次顺序会按这里的排列展示。</p>
            <article v-for="(recipient, index) in form.recipients" :key="index" class="recipient-row" :class="{ optional: index > 0 }">
              <span class="recipient-position">{{ index + 1 }}</span>
              <label class="field-group">
                <span>{{ index === 0 ? '获奖选手' : `第 ${index + 1} 位（可选）` }}</span>
                <select v-model="recipient.player_id" :required="index === 0">
                  <option value="">{{ index === 0 ? '选择选手' : '不设置' }}</option>
                  <option v-for="player in availablePlayers(index)" :key="player.player_id" :value="player.player_id">{{ player.name }}</option>
                </select>
              </label>
              <label class="field-group reason-field">
                <span>选择理由</span>
                <textarea v-model.trim="recipient.reason" :required="Boolean(recipient.player_id)" maxlength="500" :disabled="!recipient.player_id" placeholder="写清这一位为什么入选，公开页会原样展示。"></textarea>
              </label>
            </article>
          </fieldset>

          <p v-if="message" class="inline-alert" :class="messageType" role="status"><AppIcon :name="messageType === 'error' ? 'alert' : 'check'" /><span>{{ message }}</span></p>
          <div class="form-actions">
            <button class="button primary" type="submit" :disabled="saving || !players.length">
              <span v-if="saving" class="button-spinner"></span><AppIcon v-else name="save" />{{ saving ? '保存中…' : editingId ? '保存修改' : '添加到荣誉展' }}
            </button>
          </div>
        </form>
      </section>

      <section class="panel honour-award-list" aria-labelledby="honour-list-title">
        <div class="panel-header"><div><h2 id="honour-list-title">已添加奖项</h2><p>共 {{ awards.length }} 项评审特别奖</p></div><span class="result-count">{{ awards.length }}</span></div>
        <div v-if="awards.length" class="curated-awards">
          <article v-for="award in awards" :key="award.id" class="curated-award">
            <header><div><span>CURATED · {{ award.recipients.length }} 人</span><h3>{{ award.title }}</h3></div><div><button class="icon-button" type="button" :aria-label="`编辑 ${award.title}`" @click="editAward(award)"><AppIcon name="edit" /></button><button class="icon-button danger" type="button" :aria-label="`删除 ${award.title}`" @click="removeAward(award)"><AppIcon name="trash" /></button></div></header>
            <p>{{ award.description }}</p>
            <ol>
              <li v-for="(recipient, index) in award.recipients" :key="recipient.player_id">
                <span>{{ index + 1 }}</span><div><strong>{{ recipient.name }}</strong><small>{{ recipient.reason }}</small></div>
              </li>
            </ol>
          </article>
        </div>
        <div v-else class="empty-state compact"><span><AppIcon name="trophy" :size="22" /></span><h3>还没有手动奖项</h3><p>左侧填写第一项，保存后会直接出现在荣誉展的“评审特别奖”分类。</p></div>
      </section>
    </div>
  </AdminLayout>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import AdminLayout from '../components/AdminLayout.vue'
import AppIcon from '../components/AppIcon.vue'

const route = useRoute()
const router = useRouter()
const seasons = ref([])
const cup = ref('')
const players = ref([])
const awards = ref([])
const snapshotAt = ref('')
const loading = ref(true)
const saving = ref(false)
const editingId = ref(null)
const message = ref('')
const messageType = ref('success')

const blankRecipients = () => Array.from({ length: 3 }, () => ({ player_id: '', reason: '' }))
const form = reactive({ title: '', description: '', recipients: blankRecipients() })
const snapshotLabel = computed(() => snapshotAt.value ? formatDate(snapshotAt.value) : '首次访问时生成')

function displaySeason(season) { return season.cup_alias || season.name || season.cup_name }
function formatDate(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
function show(text, type = 'success') { message.value = text; messageType.value = type }
function availablePlayers(index) {
  const selected = new Set(form.recipients.map((item, itemIndex) => itemIndex === index ? '' : item.player_id))
  return players.value.filter((player) => !selected.has(player.player_id) || player.player_id === form.recipients[index].player_id)
}
function resetForm() {
  editingId.value = null
  form.title = ''
  form.description = ''
  form.recipients = blankRecipients()
  message.value = ''
}
async function loadHonours() {
  if (!cup.value) { players.value = []; awards.value = []; snapshotAt.value = ''; loading.value = false; return }
  loading.value = true
  message.value = ''
  try {
    const data = await api.get(`/api/admin/honours?cup=${encodeURIComponent(cup.value)}`)
    players.value = data.players || []
    awards.value = data.awards || []
    snapshotAt.value = data.snapshot_calculated_at || ''
  } catch (error) { show(error.message, 'error') } finally { loading.value = false }
}
async function changeSeason() {
  resetForm()
  await router.replace({ path: '/admin/honours', query: cup.value ? { cup: cup.value } : {} })
  await loadHonours()
}
function editAward(award) {
  editingId.value = award.id
  form.title = award.title
  form.description = award.description
  form.recipients = blankRecipients().map((empty, index) => award.recipients[index] ? {
    player_id: award.recipients[index].player_id,
    reason: award.recipients[index].reason,
  } : empty)
  message.value = ''
  document.getElementById('honour-composer-title')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
async function saveAward() {
  const recipients = form.recipients.filter((item) => item.player_id).map((item) => ({ player_id: item.player_id, reason: item.reason }))
  if (!recipients.length) { show('请至少选择一名获奖选手。', 'error'); return }
  if (recipients.some((item) => !item.reason.trim())) { show('请为每名获奖选手填写选择理由。', 'error'); return }
  saving.value = true
  try {
    const body = { cup: cup.value, title: form.title, description: form.description, recipients }
    if (editingId.value) await api.patch(`/api/admin/honours/${editingId.value}`, body)
    else await api.post('/api/admin/honours', body)
    const copy = editingId.value ? '奖项修改已同步到荣誉展。' : '奖项已添加到荣誉展。'
    resetForm()
    await loadHonours()
    show(copy)
  } catch (error) { show(error.message, 'error') } finally { saving.value = false }
}
async function removeAward(award) {
  if (!window.confirm(`确定删除“${award.title}”吗？公开荣誉展会同时移除。`)) return
  try {
    await api.delete(`/api/admin/honours/${award.id}?cup=${encodeURIComponent(cup.value)}`)
    if (editingId.value === award.id) resetForm()
    await loadHonours()
    show('奖项已删除。')
  } catch (error) { show(error.message, 'error') }
}

onMounted(async () => {
  try {
    const data = await api.get('/api/admin/season/list')
    seasons.value = data.seasons || []
    const requested = typeof route.query.cup === 'string' ? route.query.cup : ''
    cup.value = seasons.value.some((season) => season.cup_name === requested) ? requested : (seasons.value[0]?.cup_name || '')
    await loadHonours()
  } catch (error) { show(error.message, 'error'); loading.value = false }
})
</script>

<style scoped>
.honour-season-bar { display: grid; grid-template-columns: minmax(0, 1fr) minmax(220px, 320px) minmax(180px, auto); align-items: center; gap: var(--space-lg); margin-bottom: var(--space-lg); padding: var(--space-md) var(--space-lg); }
.honour-season-bar > div:first-child { display: flex; min-width: 0; align-items: center; gap: var(--space-sm); }
.honour-season-bar h2 { font-family: var(--font-display); font-size: var(--text-lg); }
.honour-season-bar p, .panel-header p { margin-top: var(--space-3xs); color: var(--ink-500); font-size: var(--text-xs); }
.honour-admin-mark { display: grid; width: 48px; height: 48px; flex: 0 0 auto; place-items: center; border-radius: var(--radius-md); background: var(--ink-950); color: var(--color-gold-bright); }
.honour-season-select { margin: 0; }
.honour-season-select > span, .honour-snapshot > span { color: var(--ink-500); font-size: var(--text-xs); font-weight: 700; }
.honour-snapshot { display: grid; gap: var(--space-3xs); border-left: 1px solid var(--line); padding-left: var(--space-lg); }
.honour-snapshot strong { font-size: var(--text-sm); }
.honour-admin-grid { display: grid; grid-template-columns: minmax(420px, .82fr) minmax(0, 1.18fr); gap: var(--space-lg); align-items: start; }
.honour-composer { position: sticky; top: var(--space-md); }
.honour-form { display: grid; gap: var(--space-md); padding: var(--space-lg); }
.recipient-fieldset { display: grid; gap: var(--space-sm); border: 0; }
.recipient-fieldset legend { font-family: var(--font-display); font-size: var(--text-base); font-weight: 800; }
.recipient-fieldset > p { margin-top: calc(-1 * var(--space-xs)); color: var(--ink-500); font-size: var(--text-xs); }
.recipient-row { display: grid; grid-template-columns: 38px minmax(120px, .72fr) minmax(0, 1.28fr); gap: var(--space-xs); align-items: start; border: 1px solid var(--line); padding: var(--space-sm); background: var(--surface-soft); }
.recipient-row.optional { background: var(--surface); }
.recipient-position { display: grid; width: 32px; height: 32px; place-items: center; margin-top: 25px; border-radius: 50%; background: var(--ink-950); color: var(--color-gold-bright); font-family: var(--font-outlier); font-size: var(--text-xs); font-weight: 800; }
.reason-field textarea { min-height: 74px; }
.curated-awards { display: grid; }
.curated-award { border-bottom: 1px solid var(--line); padding: var(--space-lg); }
.curated-award:last-child { border-bottom: 0; }
.curated-award > header { display: flex; align-items: flex-start; justify-content: space-between; gap: var(--space-sm); }
.curated-award > header > div:last-child { display: flex; gap: var(--space-3xs); }
.curated-award header span { color: var(--signal-dark); font-family: var(--font-outlier); font-size: .65rem; font-weight: 800; letter-spacing: .08em; }
.curated-award h3 { margin-top: var(--space-3xs); font-family: var(--font-display); font-size: var(--text-lg); }
.curated-award > p { max-width: 70ch; margin-top: var(--space-xs); color: var(--ink-600); font-size: var(--text-sm); line-height: 1.65; }
.curated-award ol { display: grid; gap: var(--space-xs); margin-top: var(--space-md); list-style: none; }
.curated-award li { display: grid; grid-template-columns: 30px minmax(0, 1fr); gap: var(--space-xs); align-items: start; }
.curated-award li > span { display: grid; width: 26px; height: 26px; place-items: center; border: 1px solid var(--line-strong); border-radius: 50%; color: var(--ink-600); font-family: var(--font-outlier); font-size: .65rem; }
.curated-award li div { display: grid; gap: var(--space-3xs); }
.curated-award li small { color: var(--ink-500); font-size: var(--text-xs); line-height: 1.5; }
.icon-button.danger { color: var(--danger); }
@media (max-width: 68rem) { .honour-season-bar { grid-template-columns: 1fr 1fr; } .honour-season-bar > div:first-child { grid-column: 1 / -1; } .honour-admin-grid { grid-template-columns: 1fr; } .honour-composer { position: static; } }
@media (max-width: 45rem) { .honour-season-bar { grid-template-columns: 1fr; padding: var(--space-sm); } .honour-season-bar > div:first-child { grid-column: auto; } .honour-snapshot { border-top: 1px solid var(--line); border-left: 0; padding-top: var(--space-sm); padding-left: 0; } .recipient-row { grid-template-columns: 32px minmax(0, 1fr); } .reason-field { grid-column: 2; } .recipient-position { margin-top: 25px; } .honour-form, .curated-award { padding: var(--space-sm); } }
</style>
