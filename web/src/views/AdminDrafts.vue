<template>
  <AdminLayout title="选人记录" description="查看自动保存的选人终稿，清理重复轮次或测试数据。">
    <template #actions>
      <router-link class="button subtle" to="/draft" target="_blank">
        <AppIcon name="external" />查看公开页面
      </router-link>
    </template>

    <section class="metric-grid draft-metrics" aria-label="选人记录概览">
      <article class="metric-card">
        <span class="metric-icon blue"><AppIcon name="archive" /></span>
        <div><strong>{{ totalCount }}</strong><span>全部记录</span></div>
        <small>包含已被替代的历史终稿</small>
      </article>
      <article class="metric-card">
        <span class="metric-icon green"><AppIcon name="check" /></span>
        <div><strong>{{ records.counts?.complete || 0 }}</strong><span>当前终稿</span></div>
        <small>会显示在公开选人页</small>
      </article>
      <article class="metric-card">
        <span class="metric-icon slate"><AppIcon name="refresh" /></span>
        <div><strong>{{ records.counts?.superseded || 0 }}</strong><span>已被替代</span></div>
        <small>重摇后保留的旧版本</small>
      </article>
    </section>

    <section class="panel draft-records" aria-labelledby="draft-records-title">
      <div class="panel-header">
        <div><h2 id="draft-records-title">保存记录</h2><p>删除后，该轮的队伍和选手明细也会一并移除。</p></div>
        <span class="result-count">{{ records.items?.length || 0 }} 条</span>
      </div>
      <div class="data-toolbar">
        <label class="select-field compact">
          <AppIcon name="filter" />
          <select v-model="status" aria-label="按状态筛选" @change="load">
            <option value="">全部状态</option>
            <option value="complete">当前终稿</option>
            <option value="superseded">已被替代</option>
          </select>
        </label>
        <span class="toolbar-summary">可根据日期、完成时间和队长确认要清理的轮次</span>
        <span class="toolbar-spacer"></span>
        <button class="icon-button" type="button" aria-label="刷新选人记录" title="刷新" :disabled="loading" @click="load">
          <AppIcon name="refresh" :class="{ spinning: loading }" />
        </button>
      </div>

      <div v-if="loading" class="loading-state compact"><span class="loader"></span><p>正在读取选人记录…</p></div>
      <div v-else-if="records.items?.length" class="table-scroll">
        <table class="data-table draft-record-table">
          <thead><tr><th>记录</th><th>比赛日</th><th>完成时间</th><th>状态</th><th>规模</th><th>队长</th><th></th></tr></thead>
          <tbody>
            <tr v-for="item in records.items" :key="item.id">
              <td><strong>#{{ item.id }}</strong><small>{{ durationLabel(item) }}</small></td>
              <td>{{ formatDay(item.play_day) }}</td>
              <td>{{ formatTime(item.completed_at) }}</td>
              <td><span class="status-badge" :class="item.status === 'complete' ? 'success' : 'neutral'"><span class="status-dot"></span>{{ statusLabel(item.status) }}</span></td>
              <td><strong>{{ item.team_count }} 队</strong><small>{{ item.player_count }} 人 · {{ item.group_count }} 组对阵</small></td>
              <td class="captain-cell" :title="captainLabel(item)">{{ captainLabel(item) }}</td>
              <td class="action-cell">
                <div class="row-actions">
                  <router-link v-if="item.status === 'complete'" class="button subtle small" :to="draftLink(item)" target="_blank"><AppIcon name="external" />查看</router-link>
                  <button class="button danger-ghost small" type="button" :disabled="Boolean(deletingId)" @click="remove(item)">
                    <span v-if="deletingId === item.id" class="button-spinner dark"></span><AppIcon v-else name="trash" />{{ deletingId === item.id ? '删除中' : '删除' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="empty-state compact"><span><AppIcon name="archive" /></span><h3>暂无选人记录</h3><p>{{ status ? '当前筛选条件下没有记录。' : '监听到完整选人终稿后，记录会显示在这里。' }}</p></div>
    </section>

    <div v-if="toast.message" class="toast" :class="toast.type" :role="toast.type === 'error' ? 'alert' : 'status'"><AppIcon :name="toast.type === 'error' ? 'alert' : 'check'" />{{ toast.message }}</div>
  </AdminLayout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api'
import { draftRoute, formatDraftClock, formatDraftDay } from '../draft'
import AdminLayout from '../components/AdminLayout.vue'
import AppIcon from '../components/AppIcon.vue'

const records = ref({ items: [], counts: {} })
const status = ref('')
const loading = ref(true)
const deletingId = ref(0)
const toast = ref({ message: '', type: 'success' })
let toastTimer

const totalCount = computed(() => Object.values(records.value.counts || {}).reduce((sum, value) => sum + Number(value || 0), 0))
const formatDay = formatDraftDay
const formatTime = (value) => formatDraftClock(value, true)
const statusLabel = (value) => value === 'complete' ? '当前终稿' : value === 'superseded' ? '已被替代' : value
const captainLabel = (item) => item.captains?.join('、') || '未记录'
const draftLink = (item) => draftRoute(item.play_day, item.id)

function durationLabel(item) {
  if (!item.started_at || !item.completed_at) return '未记录开始时间'
  const seconds = Math.max(0, Math.round((new Date(item.completed_at) - new Date(item.started_at)) / 1000))
  if (!Number.isFinite(seconds)) return '未记录开始时间'
  return `用时 ${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}
function show(message, type = 'success') {
  clearTimeout(toastTimer)
  toast.value = { message, type }
  toastTimer = setTimeout(() => { toast.value.message = '' }, 3500)
}
async function load() {
  loading.value = true
  try {
    const query = status.value ? `?status=${encodeURIComponent(status.value)}` : ''
    records.value = await api.get(`/api/admin/drafts${query}`)
  } catch (error) {
    show(error.message, 'error')
  } finally {
    loading.value = false
  }
}
async function remove(item) {
  const label = `${formatDay(item.play_day)} ${formatTime(item.completed_at)} 的 #${item.id} 记录`
  if (!window.confirm(`确认永久删除${label}？\n\n该轮队伍与选手明细会一并删除，此操作无法撤销。`)) return
  deletingId.value = item.id
  try {
    const result = await api.delete(`/api/admin/drafts/${item.id}`)
    show(result.message || '选人记录已删除')
    await load()
  } catch (error) {
    show(error.message, 'error')
  } finally {
    deletingId.value = 0
  }
}

onMounted(load)
onBeforeUnmount(() => clearTimeout(toastTimer))
</script>

<style scoped>
.draft-metrics { margin-bottom: 18px; }
.draft-records { overflow: hidden; }
.draft-records .data-toolbar { min-height: 64px; }
.draft-record-table { min-width: 920px; }
.draft-record-table td:first-child strong, .draft-record-table td:nth-child(5) strong { color: var(--ink-800); }
.captain-cell { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 760px) {
  .draft-records .data-toolbar { align-items: stretch; flex-wrap: wrap; }
  .draft-records .toolbar-summary { width: 100%; white-space: normal; }
  .draft-records .toolbar-spacer { display: none; }
}
</style>
