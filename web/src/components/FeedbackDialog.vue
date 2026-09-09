<template>
  <AppModal
    :open="open"
    :title="copy.title"
    :eyebrow="copy.eyebrow"
    :description="copy.description"
    size="large"
    :persistent="submitting"
    @close="$emit('close')"
  >
    <div v-if="submitted" class="feedback-received" role="status">
      <span><AppIcon name="check" :size="28" /></span>
      <h3>{{ submitted.duplicate ? '这条想法已经记下了' : copy.successTitle }}</h3>
      <p>{{ copy.successDescription }}</p>
      <code>{{ submitted.reference }}</code>
      <div class="form-actions">
        <button class="button subtle" type="button" @click="resetForm">再写一条</button>
        <button class="button primary" type="button" @click="$emit('close')">完成</button>
      </div>
    </div>
    <div v-else class="feedback-dialog-grid" :class="{ 'has-history': history.length }">
      <form class="feedback-form" @submit.prevent="submit">
        <div class="field-group">
          <div class="label-line"><label :for="`${formId}-subject`">{{ copy.subjectLabel }}</label><output>{{ form.subject.length }}/120</output></div>
          <input :id="`${formId}-subject`" v-model="form.subject" required maxlength="120" :placeholder="copy.subjectPlaceholder" :disabled="submitting">
        </div>
        <div class="field-group">
          <div class="label-line"><label :for="`${formId}-content`">{{ copy.contentLabel }}</label><output>{{ form.content.length }}/800</output></div>
          <textarea :id="`${formId}-content`" v-model="form.content" required maxlength="800" :placeholder="copy.contentPlaceholder" :disabled="submitting"></textarea>
          <small v-if="copy.contentHint">{{ copy.contentHint }}</small>
        </div>
        <div v-for="field in detailFields" :key="field.key" class="field-group">
          <div class="label-line"><label :for="`${formId}-${field.key}`">{{ field.label }}</label><output>{{ (form.details[field.key] || '').length }}/{{ field.maxlength || 400 }}</output></div>
          <textarea v-if="field.multiline !== false" :id="`${formId}-${field.key}`" v-model="form.details[field.key]" :maxlength="field.maxlength || 400" :placeholder="field.placeholder" :disabled="submitting"></textarea>
          <input v-else :id="`${formId}-${field.key}`" v-model="form.details[field.key]" :maxlength="field.maxlength || 400" :placeholder="field.placeholder" :disabled="submitting">
        </div>
        <div class="field-group">
          <div class="label-line"><label :for="`${formId}-name`">{{ copy.submitterLabel }}</label><output>{{ form.submitterName.length }}/64</output></div>
          <input :id="`${formId}-name`" v-model="form.submitterName" maxlength="64" :placeholder="copy.submitterPlaceholder" autocomplete="nickname" :disabled="submitting">
        </div>
        <label class="feedback-honeypot" aria-hidden="true">网站<input v-model="form.website" tabindex="-1" autocomplete="off"></label>
        <p v-if="submitError" class="inline-field-error" role="alert">{{ submitError }}</p>
        <div class="form-actions">
          <button class="button subtle" type="button" :disabled="submitting" @click="$emit('close')">暂不提交</button>
          <button class="button primary" type="submit" :disabled="submitting || !form.subject.trim() || !form.content.trim()">
            <span v-if="submitting" class="button-spinner"></span><AppIcon v-else name="message" />{{ submitting ? '正在投递' : copy.submitLabel }}
          </button>
        </div>
      </form>

      <aside v-if="history.length" class="feedback-history" aria-label="我的近期反馈">
        <header><span>MY NOTES</span><h3>{{ copy.historyTitle }}</h3></header>
        <article v-for="item in history" :key="item.reference" :class="{ replied: item.reply }">
          <div><strong>{{ item.subject }}</strong><span>{{ statusLabel(item.status) }}</span></div>
          <p v-if="item.reply"><b>管理员回复</b>{{ item.reply }}</p>
          <small>{{ formatDate(item.created_at) }} · {{ item.reference }}</small>
        </article>
      </aside>
    </div>
  </AppModal>
</template>

<script setup>
import { reactive, ref, watch } from 'vue'
import { api } from '../api'
import { FEEDBACK_STORAGE_KEY, feedbackPayload, mergeFeedbackReference, relevantFeedbackReferences } from '../feedback'
import AppIcon from './AppIcon.vue'
import AppModal from './AppModal.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  type: { type: String, required: true },
  context: { type: Object, required: true },
  copy: { type: Object, required: true },
  detailFields: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'submitted'])
const formId = `feedback-${Math.random().toString(36).slice(2, 9)}`
const form = reactive({ subject: '', content: '', submitterName: '', details: {}, website: '' })
const submitting = ref(false)
const submitted = ref(null)
const submitError = ref('')
const history = ref([])

function storedReferences() {
  try {
    const value = JSON.parse(localStorage.getItem(FEEDBACK_STORAGE_KEY) || '[]')
    return Array.isArray(value) ? value : []
  } catch { return [] }
}
function saveReference(result) {
  const entries = mergeFeedbackReference(storedReferences(), {
    reference: result.reference, type: props.type, context_id: String(props.context.id || ''),
  })
  try { localStorage.setItem(FEEDBACK_STORAGE_KEY, JSON.stringify(entries)) } catch { /* 提交仍然有效，仅无法在本机保留查询编号 */ }
}
async function loadHistory() {
  const references = relevantFeedbackReferences(
    storedReferences(), props.type, String(props.context.id || ''),
  )
  const results = await Promise.all(references.map(async (item) => {
    try { return await api.feedbackStatus(item.reference) } catch { return null }
  }))
  history.value = results.filter(Boolean)
}
function resetForm() {
  form.subject = ''; form.content = ''; form.submitterName = ''; form.details = {}; form.website = ''
  submitted.value = null; submitError.value = ''
}
async function submit() {
  submitting.value = true
  submitError.value = ''
  try {
    const result = await api.submitFeedback(feedbackPayload({
      type: props.type, subject: form.subject, content: form.content,
      submitterName: form.submitterName, context: props.context,
      details: form.details, sourcePath: window.location.pathname, website: form.website,
    }))
    submitted.value = result
    if (result.reference) saveReference(result)
    await loadHistory()
    emit('submitted', result)
  } catch (error) {
    submitError.value = error.message || '提交失败，请稍后再试。'
  } finally { submitting.value = false }
}
function statusLabel(status) { return ({ new: '待处理', reviewing: '处理中', replied: '已回复', closed: '已关闭' }[status] || '已收到') }
function formatDate(value) { return value ? value.replace('T', ' ').slice(0, 16) : '' }

watch(() => props.open, (open) => {
  if (open) { submitted.value = null; submitError.value = ''; loadHistory() }
})
</script>

<style scoped>
.feedback-dialog-grid { display: grid; }
.feedback-dialog-grid.has-history { grid-template-columns: minmax(0, 1.35fr) minmax(230px, .65fr); }
.feedback-form { display: grid; gap: 16px; padding: 20px 22px 22px; }
.feedback-form textarea { min-height: 112px; }
.feedback-form .form-actions { border-top: 1px solid var(--line); padding-top: 16px; }
.feedback-honeypot { position: absolute; left: -10000px; width: 1px; height: 1px; overflow: hidden; }
.feedback-history { max-height: 560px; overflow-y: auto; border-left: 1px solid var(--line); padding: 20px; background: var(--surface-soft); }
.feedback-history header span { color: var(--signal-dark); font-family: var(--font-outlier); font-size: .62rem; letter-spacing: .1em; }
.feedback-history header h3 { margin-top: 3px; font-family: var(--font-display); font-size: 1rem; }
.feedback-history article { margin-top: 12px; border: 1px solid var(--line); border-left: 3px solid var(--line-strong); border-radius: var(--radius-input); padding: 11px; background: var(--surface); }
.feedback-history article.replied { border-left-color: var(--signal); }
.feedback-history article > div { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
.feedback-history article strong { font-size: .76rem; }
.feedback-history article > div span { flex: 0 0 auto; color: var(--ink-500); font-size: .62rem; }
.feedback-history article p { display: grid; gap: 3px; margin-top: 9px; border-radius: 6px; padding: 8px; background: var(--signal-soft); color: var(--ink-700); font-size: .7rem; line-height: 1.55; }
.feedback-history article p b { color: var(--signal-dark); font-size: .62rem; }
.feedback-history article small { display: block; margin-top: 8px; color: var(--ink-500); font-family: var(--font-outlier); font-size: .56rem; }
.feedback-received { display: grid; min-height: 380px; place-content: center; justify-items: center; padding: 32px; text-align: center; }
.feedback-received > span { display: grid; width: 64px; height: 64px; place-items: center; border-radius: 50%; background: var(--signal-soft); color: var(--signal-dark); }
.feedback-received h3 { margin-top: 16px; font-family: var(--font-display); font-size: 1.35rem; }
.feedback-received p { max-width: 34ch; margin-top: 6px; color: var(--ink-500); font-size: .78rem; line-height: 1.6; }
.feedback-received code { margin-top: 14px; border: 1px solid var(--line); border-radius: 6px; padding: 5px 8px; background: var(--surface-soft); color: var(--ink-600); font-size: .66rem; }
.feedback-received .form-actions { margin-top: 18px; }
@media (max-width: 700px) {
  .feedback-dialog-grid.has-history { grid-template-columns: 1fr; }
  .feedback-form { padding: 16px; }
  .feedback-history { max-height: none; border-top: 1px solid var(--line); border-left: 0; }
}
</style>
