<template>
  <AdminLayout title="反馈收件箱" description="查看公开页面收到的想法，记录处理进度并回复提交者。">
    <section class="metric-grid feedback-metrics" aria-label="反馈状态概览">
      <article v-for="metric in metrics" :key="metric.key" class="metric-card">
        <span class="metric-icon" :class="metric.tone"><AppIcon :name="metric.icon" /></span>
        <div><strong>{{ inbox.counts?.[metric.key] || 0 }}</strong><span>{{ metric.label }}</span></div>
        <small>{{ metric.note }}</small>
      </article>
    </section>

    <section class="panel feedback-toolbar" aria-label="筛选反馈">
      <form @submit.prevent="load(1)">
        <label class="search-field"><AppIcon name="search" /><input v-model="filters.q" type="search" placeholder="搜索奖项名、含义或署名"></label>
        <label class="field-group"><span>类型</span><select v-model="filters.type" @change="load(1)"><option value="">全部类型</option><option v-for="type in inbox.types" :key="type.key" :value="type.key">{{ type.label }}</option></select></label>
        <label class="field-group"><span>状态</span><select v-model="filters.status" @change="load(1)"><option value="">全部状态</option><option v-for="(label, key) in statusLabels" :key="key" :value="key">{{ label }}</option></select></label>
        <button class="button subtle" type="submit"><AppIcon name="filter" />筛选</button>
      </form>
    </section>

    <div v-if="loading" class="loading-state"><span class="loader"></span><p>正在读取反馈…</p></div>
    <div v-else class="feedback-inbox-layout">
      <aside class="panel feedback-list" aria-label="反馈列表">
        <header><div><span>INBOX</span><h2>收到的反馈</h2></div><b>{{ inbox.total || 0 }} 条</b></header>
        <div v-if="inbox.items?.length" class="feedback-list-items">
          <button v-for="item in inbox.items" :key="item.reference" type="button" :class="{ active: selected?.reference === item.reference }" @click="select(item)">
            <span class="feedback-list-top"><em>{{ item.type_label }}</em><i :class="`status-${item.status}`">{{ statusLabels[item.status] }}</i></span>
            <strong>{{ item.subject }}</strong>
            <p>{{ item.content }}</p>
            <small>{{ item.submitter_name || '匿名水友' }} · {{ formatTime(item.created_at) }}</small>
          </button>
        </div>
        <div v-else class="empty-state compact"><span><AppIcon name="message" /></span><h3>没有符合条件的反馈</h3><p>调整筛选条件，或等待水友提交新的想法。</p></div>
        <footer v-if="pageCount > 1"><button class="button subtle small" type="button" :disabled="inbox.page <= 1" @click="load(inbox.page - 1)">上一页</button><span>{{ inbox.page }} / {{ pageCount }}</span><button class="button subtle small" type="button" :disabled="inbox.page >= pageCount" @click="load(inbox.page + 1)">下一页</button></footer>
      </aside>

      <section class="panel feedback-reader" aria-live="polite">
        <div v-if="!selected" class="empty-state"><span><AppIcon name="message" /></span><h3>选择一条反馈</h3><p>完整内容、上下文与回复操作会显示在这里。</p></div>
        <template v-else>
          <header class="feedback-reader-header">
            <div><span>{{ selected.type_label }} · {{ selected.reference }}</span><h2>{{ selected.subject }}</h2></div>
            <span class="status-badge" :class="statusTone(selected.status)"><span class="status-dot"></span>{{ statusLabels[selected.status] }}</span>
          </header>
          <div class="feedback-reader-body">
            <dl class="feedback-facts"><div><dt>提交者</dt><dd>{{ selected.submitter_name || '匿名水友' }}</dd></div><div><dt>来源</dt><dd>{{ selected.context?.label || selected.context_id }}</dd></div><div><dt>提交时间</dt><dd>{{ formatTime(selected.created_at, true) }}</dd></div></dl>
            <article class="feedback-content"><span>反馈内容</span><p>{{ selected.content }}</p></article>
            <article v-if="detailEntries.length" class="feedback-details"><span>补充信息</span><dl><div v-for="([key, value]) in detailEntries" :key="key"><dt>{{ detailLabels[key] || key }}</dt><dd>{{ formatDetail(value) }}</dd></div></dl></article>
            <a v-if="selected.source_path" class="feedback-source" :href="selected.source_path" target="_blank" rel="noopener"><AppIcon name="external" :size="15" />打开来源页面</a>
          </div>
          <form class="feedback-reply" @submit.prevent="saveReply">
            <div class="feedback-reply-heading"><div><span>RESPONSE</span><h3>处理与回复</h3></div><label class="field-group"><span>状态</span><select v-model="statusDraft" :disabled="saving"><option v-for="(label, key) in statusLabels" :key="key" :value="key">{{ label }}</option></select></label></div>
            <div class="field-group"><div class="label-line"><label for="feedback-reply">回复内容</label><output>{{ replyDraft.length }}/1200</output></div><textarea id="feedback-reply" v-model="replyDraft" maxlength="1200" placeholder="回复会在提交者的“我的近期提名”中显示。" :disabled="saving"></textarea></div>
            <p v-if="selected.replied_at" class="reply-meta">上次由 {{ selected.replied_by || '管理员' }} 回复于 {{ formatTime(selected.replied_at, true) }}</p>
            <div class="form-actions"><button class="button primary" type="submit" :disabled="saving"><span v-if="saving" class="button-spinner"></span><AppIcon v-else name="message" />{{ saving ? '正在保存' : '保存处理结果' }}</button></div>
          </form>
        </template>
      </section>
    </div>
    <div v-if="toast.message" class="toast" :class="toast.type" :role="toast.type === 'error' ? 'alert' : 'status'"><AppIcon :name="toast.type === 'error' ? 'alert' : 'check'" />{{ toast.message }}</div>
  </AdminLayout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import AdminLayout from '../components/AdminLayout.vue'
import AppIcon from '../components/AppIcon.vue'

const inbox = ref({ items: [], counts: {}, types: [], total: 0, page: 1, page_size: 40 })
const filters = reactive({ q: '', type: '', status: '' })
const selected = ref(null)
const loading = ref(true)
const saving = ref(false)
const replyDraft = ref('')
const statusDraft = ref('new')
const toast = ref({ message: '', type: 'success' })
let toastTimer
const statusLabels = { new: '待处理', reviewing: '处理中', replied: '已回复', closed: '已关闭' }
const detailLabels = { method: '建议算法' }
const metrics = [
  { key: 'new', label: '待处理', note: '等待首次查看', tone: 'amber', icon: 'message' },
  { key: 'reviewing', label: '处理中', note: '正在评估', tone: 'blue', icon: 'activity' },
  { key: 'replied', label: '已回复', note: '水友可查看', tone: 'green', icon: 'check' },
  { key: 'closed', label: '已关闭', note: '处理已结束', tone: 'slate', icon: 'archive' },
]
const pageCount = computed(() => Math.max(1, Math.ceil((inbox.value.total || 0) / (inbox.value.page_size || 40))))
const detailEntries = computed(() => Object.entries(selected.value?.details || {}).filter(([, value]) => value !== '' && value != null))

function show(message, type = 'success') { clearTimeout(toastTimer); toast.value = { message, type }; toastTimer = setTimeout(() => { toast.value.message = '' }, 3500) }
function formatTime(value, seconds = false) { return value ? value.replace('T', ' ').slice(0, seconds ? 19 : 16) : '未记录' }
function formatDetail(value) { return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value) }
function statusTone(status) { return status === 'replied' ? 'success' : status === 'reviewing' ? 'running' : 'neutral' }
function select(item) { selected.value = item; replyDraft.value = item.reply || ''; statusDraft.value = item.status || 'new' }
async function load(page = 1) {
  loading.value = true
  try {
    const query = new URLSearchParams({ page: String(page), page_size: '40' })
    if (filters.q.trim()) query.set('q', filters.q.trim())
    if (filters.type) query.set('type', filters.type)
    if (filters.status) query.set('status', filters.status)
    inbox.value = await api.get(`/api/admin/feedback?${query}`)
    const current = inbox.value.items.find((item) => item.reference === selected.value?.reference)
    select(current || inbox.value.items[0] || null)
  } catch (error) { show(error.message, 'error') } finally { loading.value = false }
}
async function saveReply() {
  if (!selected.value) return
  saving.value = true
  try {
    const reply = replyDraft.value.trim()
    const status = reply && ['new', 'reviewing'].includes(statusDraft.value) ? 'replied' : statusDraft.value
    const updated = await api.patch(`/api/admin/feedback/${encodeURIComponent(selected.value.reference)}`, { status, reply })
    selected.value = updated; replyDraft.value = updated.reply || ''; statusDraft.value = updated.status
    show(reply ? '回复已保存，提交者现在可以查看' : '处理状态已保存')
    await load(inbox.value.page)
  } catch (error) { show(error.message, 'error') } finally { saving.value = false }
}

onMounted(() => load())
onBeforeUnmount(() => clearTimeout(toastTimer))
</script>

<style scoped>
.feedback-metrics { margin-bottom: 18px; }
.feedback-toolbar { margin-bottom: 18px; padding: 14px; }
.feedback-toolbar form { display: grid; grid-template-columns: minmax(240px, 1fr) 180px 160px auto; gap: 10px; align-items: end; }
.feedback-toolbar .field-group { gap: 4px; }
.feedback-toolbar .field-group > span { color: var(--ink-500); font-size: .65rem; font-weight: 700; }
.feedback-inbox-layout { display: grid; grid-template-columns: minmax(300px, .72fr) minmax(500px, 1.28fr); gap: 18px; align-items: start; }
.feedback-list { overflow: hidden; }
.feedback-list > header { display: flex; min-height: 72px; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--line); padding: 14px 16px; }
.feedback-list > header span, .feedback-reader-header > div > span, .feedback-reply-heading > div > span, .feedback-content > span, .feedback-details > span { color: var(--signal-dark); font-family: var(--font-outlier); font-size: .58rem; letter-spacing: .09em; }
.feedback-list > header h2 { margin-top: 2px; font-family: var(--font-display); font-size: 1rem; }
.feedback-list > header b { color: var(--ink-500); font-size: .7rem; }
.feedback-list-items { max-height: 690px; overflow-y: auto; }
.feedback-list-items > button { display: grid; width: 100%; gap: 5px; border-bottom: 1px solid var(--line); padding: 14px 16px; background: var(--surface); text-align: left; transition: background var(--dur-short) var(--ease-out), box-shadow var(--dur-short) var(--ease-out); }
.feedback-list-items > button:hover { background: var(--surface-soft); }
.feedback-list-items > button.active { background: var(--signal-soft); box-shadow: inset 3px 0 var(--signal); }
.feedback-list-top { display: flex; align-items: center; justify-content: space-between; }
.feedback-list-top em { color: var(--signal-dark); font-size: .62rem; font-style: normal; font-weight: 700; }
.feedback-list-top i { color: var(--ink-500); font-size: .6rem; font-style: normal; }
.feedback-list-top i.status-new { color: var(--amber); }
.feedback-list-top i.status-replied { color: var(--signal-dark); }
.feedback-list-items strong { overflow: hidden; color: var(--ink-900); font-size: .83rem; text-overflow: ellipsis; white-space: nowrap; }
.feedback-list-items p { display: -webkit-box; overflow: hidden; color: var(--ink-600); font-size: .7rem; line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.feedback-list-items small { color: var(--ink-500); font-size: .61rem; }
.feedback-list > footer { display: flex; align-items: center; justify-content: space-between; border-top: 1px solid var(--line); padding: 10px; color: var(--ink-500); font-size: .66rem; }
.feedback-reader { overflow: hidden; }
.feedback-reader-header { display: flex; min-height: 92px; align-items: flex-start; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--line); padding: 19px 20px; }
.feedback-reader-header h2 { margin-top: 5px; font-family: var(--font-display); font-size: 1.35rem; }
.feedback-reader-body { display: grid; gap: 16px; padding: 20px; }
.feedback-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border: 1px solid var(--line); }
.feedback-facts > div { padding: 10px 12px; border-right: 1px solid var(--line); }
.feedback-facts > div:last-child { border-right: 0; }
.feedback-facts dt { color: var(--ink-500); font-size: .59rem; }
.feedback-facts dd { margin-top: 3px; color: var(--ink-800); font-size: .72rem; }
.feedback-content, .feedback-details { border-left: 3px solid var(--line-strong); padding: 5px 0 5px 14px; }
.feedback-content p { margin-top: 7px; color: var(--ink-800); font-size: .82rem; line-height: 1.75; white-space: pre-wrap; }
.feedback-details dl { margin-top: 7px; }
.feedback-details dl > div { display: grid; gap: 3px; }
.feedback-details dt { color: var(--ink-500); font-size: .64rem; }
.feedback-details dd { color: var(--ink-700); font-size: .76rem; line-height: 1.6; white-space: pre-wrap; }
.feedback-source { display: inline-flex; width: fit-content; align-items: center; gap: 6px; color: var(--signal-dark); font-size: .69rem; font-weight: 700; }
.feedback-reply { display: grid; gap: 14px; border-top: 1px solid var(--line); padding: 20px; background: var(--surface-soft); }
.feedback-reply-heading { display: flex; align-items: end; justify-content: space-between; gap: 16px; }
.feedback-reply-heading h3 { margin-top: 3px; font-family: var(--font-display); font-size: 1rem; }
.feedback-reply-heading .field-group { width: 150px; gap: 4px; }
.feedback-reply-heading .field-group > span { color: var(--ink-500); font-size: .62rem; }
.feedback-reply textarea { min-height: 140px; }
.reply-meta { color: var(--ink-500); font-size: .64rem; }
@media (max-width: 1050px) { .feedback-toolbar form { grid-template-columns: 1fr 1fr; } .feedback-inbox-layout { grid-template-columns: 1fr; } .feedback-list-items { max-height: 420px; } }
@media (max-width: 620px) { .feedback-toolbar form { grid-template-columns: 1fr; } .feedback-facts { grid-template-columns: 1fr; } .feedback-facts > div { border-right: 0; border-bottom: 1px solid var(--line); } .feedback-facts > div:last-child { border-bottom: 0; } .feedback-reader-header, .feedback-reply-heading { align-items: flex-start; flex-direction: column; } .feedback-reply-heading .field-group { width: 100%; } }
</style>
