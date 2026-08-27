<template>
  <div class="admin-shell">
    <h1>玩家库</h1>
    <div class="admin-nav">
      <router-link to="/admin/season">杯赛 / 采集</router-link>
      <router-link class="on" to="/admin/players">玩家库</router-link>
      <span class="spacer"></span>
      <router-link to="/">公开首页</router-link>
      <a href="#" @click.prevent="logout">退出</a>
    </div>
    <p class="muted">库内玩家会计入杯赛「库内占比」门槛。比赛里新出现的路人默认不进库。</p>

    <h2>编辑 / 新增</h2>
    <div class="card">
      <div class="row">
        <label>player_id*</label><input v-model="form.id" placeholder="SteamID64">
        <label>昵称</label><input v-model="form.nick">
        <label>别名</label><input v-model="form.alias" placeholder="首页展示优先用别名">
        <label>Steam ID</label><input v-model="form.steam">
        <label>库内</label>
        <select v-model="form.lib"><option value="1">是</option><option value="0">否</option></select>
        <button class="btn" @click="save">保存</button>
      </div>
    </div>

    <h2>列表</h2>
    <div class="card">
      <div class="row" style="margin-bottom:10px">
        <input v-model="q" placeholder="搜索 ID / 昵称 / 别名" @keydown.enter="load">
        <select v-model="filterLib" @change="load">
          <option value="">全部</option>
          <option value="1">仅库内</option>
          <option value="0">仅非库内</option>
        </select>
        <button class="ghost" @click="load">搜索</button>
        <span class="spacer"></span>
        <button class="btn" @click="bulk(true)">选中标为库内</button>
        <button class="danger" @click="bulk(false)">选中移出库内</button>
      </div>
      <table class="admin-table">
        <thead>
          <tr>
            <th><input type="checkbox" @change="toggleAll($event)"></th>
            <th>玩家</th><th>player_id</th><th>别名</th><th>Steam ID</th><th>库内</th><th></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="p in players" :key="p.player_id">
            <td><input type="checkbox" :value="p.player_id" v-model="checked"></td>
            <td>{{ p.nickname }}</td>
            <td class="muted">{{ p.player_id }}</td>
            <td>{{ p.alias_name }}</td>
            <td class="muted">{{ p.steam_id }}</td>
            <td><span class="tag" :class="p.in_library ? 'active' : 'archived'">{{ p.in_library ? '库内' : '路人' }}</span></td>
            <td>
              <button class="ghost sm" @click="fill(p)">编辑</button>
              <button class="btn sm" @click="setLib([p.player_id], !p.in_library)">{{ p.in_library ? '移出' : '标入库内' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="toast" class="toast">{{ toast }}</div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const players = ref([])
const q = ref('')
const filterLib = ref('')
const checked = ref([])
const toast = ref('')
const form = ref({ id: '', nick: '', alias: '', steam: '', lib: '1' })

function show(msg) {
  toast.value = msg
  setTimeout(() => { toast.value = '' }, 2000)
}
async function load() {
  const params = new URLSearchParams({ q: q.value })
  if (filterLib.value !== '') params.set('in_library', filterLib.value)
  const data = await api.get('/api/admin/players?' + params)
  players.value = data.players || []
  checked.value = []
}
function fill(p) {
  form.value = {
    id: p.player_id,
    nick: p.nickname || '',
    alias: p.alias_name || '',
    steam: p.steam_id || '',
    lib: p.in_library ? '1' : '0',
  }
}
async function save() {
  if (!form.value.id.trim()) return show('player_id 不能为空')
  const data = await api.send('/api/admin/player/save', {
    player_id: form.value.id.trim(),
    nickname: form.value.nick,
    alias_name: form.value.alias,
    steam_id: form.value.steam,
    in_library: form.value.lib,
  })
  show(typeof data === 'string' ? data : '已保存')
  load()
}
async function setLib(ids, on) {
  const data = await api.send('/api/admin/player/library', { player_ids: ids.join(','), in_library: on ? '1' : '0' })
  show(typeof data === 'string' ? data : '已更新')
  load()
}
function bulk(on) {
  if (!checked.value.length) return show('未勾选')
  setLib(checked.value, on)
}
function toggleAll(e) {
  checked.value = e.target.checked ? players.value.map((p) => p.player_id) : []
}
async function logout() {
  await api.logout()
  router.replace('/admin/login')
}
onMounted(load)
</script>
