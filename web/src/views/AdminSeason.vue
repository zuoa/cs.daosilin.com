<template>
  <AdminLayout
    eyebrow="TOURNAMENT OPS"
    title="杯赛与采集"
    description="配置统计范围、维护种子名单，并审核进入公开数据的每一场比赛。"
  >
    <template #actions>
      <router-link v-if="currentCup" class="button subtle" :to="`/${currentCup}/`">
        <AppIcon name="external" />公开统计页
      </router-link>
      <button class="button primary" type="button" @click="createSeason">
        <AppIcon name="plus" />新建杯赛
      </button>
    </template>

    <section class="metric-grid season-metrics" aria-label="杯赛管理概览">
      <article class="metric-card">
        <span class="metric-icon green"><AppIcon name="layers" /></span>
        <div><strong>{{ activeSeasons }}</strong><span>进行中杯赛</span></div>
        <small>共 {{ seasons.length }} 个杯赛</small>
      </article>
      <article class="metric-card">
        <span class="metric-icon blue"><AppIcon name="database" /></span>
        <div><strong>{{ totalApproved }}</strong><span>已纳入比赛</span></div>
        <small>{{ totalRejected }} 场已剔除</small>
      </article>
      <article class="metric-card">
        <span class="metric-icon amber"><AppIcon name="users" /></span>
        <div><strong>{{ currentSeason?.roster_count || 0 }}</strong><span>当前种子</span></div>
        <small>{{ currentSeason ? displaySeason(currentSeason) : '尚未选择杯赛' }}</small>
      </article>
      <article class="metric-card">
        <span class="metric-icon" :class="autoEnabled ? 'pulse green' : 'slate'"><AppIcon name="activity" /></span>
        <div><strong class="metric-status">{{ crawlStateLabel }}</strong><span>自动采集</span></div>
        <small>{{ currentCup || '选择杯赛后启动' }}</small>
      </article>
    </section>

    <div class="season-workbench">
      <aside class="panel season-directory season-directory-rail" aria-labelledby="season-list-title">
        <div class="panel-header">
          <div>
            <h2 id="season-list-title">杯赛目录</h2>
            <p>选择杯赛后在右侧管理</p>
          </div>
          <span class="result-count">{{ seasons.length }} 个</span>
        </div>

        <div v-if="seasonLoading" class="loading-state compact"><span class="loader"></span><p>读取杯赛…</p></div>
        <div v-else-if="seasons.length" class="season-list">
          <article
            v-for="(s, index) in seasons"
            :key="s.cup_name"
            class="season-list-item"
            :class="{ current: s.cup_name === currentCup }"
          >
            <button
              class="season-select"
              type="button"
              :aria-pressed="s.cup_name === currentCup"
              @click="selectCup(s.cup_name)"
            >
              <span class="season-index">{{ padIndex(index + 1) }}</span>
              <span class="season-list-copy">
                <span class="season-name-line">
                  <strong>{{ displaySeason(s) }}</strong>
                  <span class="status-badge" :class="s.status === 'active' ? 'success' : 'neutral'">
                    <span class="status-dot"></span>{{ s.status === 'active' ? '进行中' : '已归档' }}
                  </span>
                </span>
                <code>/{{ s.cup_name }}</code>
                <span class="season-list-meta">
                  {{ s.roster_count }} 名种子 · {{ s.approved_count || 0 }} 场比赛 · 门槛 {{ pct(s.hit_ratio) }}%
                </span>
              </span>
              <AppIcon name="chevronRight" />
            </button>
            <button class="icon-button edit-season" type="button" :aria-label="`编辑 ${displaySeason(s)}`" title="编辑杯赛" @click="editSeason(s)">
              <AppIcon name="edit" />
            </button>
          </article>
        </div>
        <div v-else class="empty-state compact">
          <span><AppIcon name="layers" :size="24" /></span>
          <h3>还没有杯赛</h3>
          <p>先建立杯赛，再配置种子并采集比赛。</p>
          <button class="button subtle" type="button" @click="createSeason">新建杯赛</button>
        </div>
      </aside>

      <main class="season-detail-workspace">
        <template v-if="currentCup">
      <div class="current-context">
        <div>
          <span class="live-indicator" :class="{ idle: currentSeason?.status !== 'active' }"></span>
          <p><small>CURRENT TOURNAMENT</small><strong>{{ currentSeason ? displaySeason(currentSeason) : currentCup }}</strong></p>
        </div>
        <code>/{{ currentCup }}</code>
      </div>

      <div class="workflow-grid">
        <section class="panel roster-panel" aria-labelledby="roster-title">
          <div class="panel-header">
            <div>
              <h2 id="roster-title">种子玩家</h2>
            </div>
            <span class="result-count">{{ seedChecked.length }} 人</span>
          </div>
          <p class="panel-intro">为自定义比赛建立可信名单。采集时会按上方设置的占比门槛判断是否纳入。</p>
          <label class="search-field full" for="seed-search">
            <AppIcon name="search" />
            <input id="seed-search" v-model="seedQ" type="search" placeholder="搜索库内玩家">
          </label>
          <div class="picker modern-picker">
            <label v-for="p in filteredLibrary" :key="p.player_id" class="picker-option">
              <input v-model="seedChecked" type="checkbox" :value="p.player_id">
              <span class="player-monogram small">{{ displayPlayer(p).slice(0, 1).toUpperCase() }}</span>
              <span><strong>{{ displayPlayer(p) }}</strong><code>{{ p.player_id }}</code></span>
              <AppIcon name="check" class="picker-check" />
            </label>
            <div v-if="!filteredLibrary.length" class="picker-empty">玩家库中没有匹配结果，可在下方直接粘贴 ID。</div>
          </div>
          <details class="manual-entry">
            <summary>手动录入 Player ID</summary>
            <div class="field-group">
              <label for="roster-raw">Player IDs</label>
              <textarea id="roster-raw" v-model="rosterRaw" placeholder="多个 ID 用逗号、空格或换行分隔"></textarea>
            </div>
          </details>
          <div class="form-actions">
            <button class="button primary" type="button" :disabled="savingRoster" @click="saveRoster">
              <span v-if="savingRoster" class="button-spinner"></span>
              <AppIcon v-else name="save" />{{ savingRoster ? '保存中…' : '保存种子名单' }}
            </button>
          </div>
        </section>

        <section class="panel crawl-panel" aria-labelledby="crawl-title">
          <div class="panel-header">
            <div>
              <h2 id="crawl-title">数据采集</h2>
            </div>
            <span class="status-badge" :class="crawling ? 'running' : autoEnabled ? 'success' : 'neutral'">
              <span class="status-dot"></span>{{ crawlStateLabel }}
            </span>
          </div>
          <div class="crawl-visual" :class="{ active: crawling }" aria-hidden="true">
            <div class="radar-ring ring-one"></div>
            <div class="radar-ring ring-two"></div>
            <div class="radar-sweep"></div>
            <AppIcon name="target" :size="40" />
          </div>
          <div class="crawl-copy">
            <strong>{{ crawlHeadline }}</strong>
            <p>{{ crawlMsg }}</p>
          </div>
          <div class="crawl-details">
            <div><span>统计范围</span><strong>{{ formatRange(currentSeason) }}</strong></div>
            <div><span>获取频率</span><strong>每 10 分钟</strong></div>
            <div><span>比赛类型</span><strong>{{ currentSeason?.match_type === 'official' ? '官方比赛' : '自定义比赛' }}</strong></div>
            <div><span>纳入规则</span><strong>库内占比 ≥ {{ pct(currentSeason?.hit_ratio) }}%</strong></div>
            <div><span>冠军统计</span><strong>{{ currentSeason?.champion_enabled ? '计算冠军 / 亚军' : '仅保留比赛与选手排名' }}</strong></div>
          </div>
          <button class="button primary crawl-button" type="button" :disabled="crawlButtonDisabled" @click="startCrawl('auto')">
            <AppIcon :name="autoEnabled ? 'activity' : 'refresh'" :class="{ spinning: crawling }" />
            {{ crawlButtonLabel }}
          </button>
          <button class="button subtle crawl-button" type="button" :disabled="manualCrawlDisabled" @click="startCrawl('once')">
            <AppIcon name="refresh" :class="{ spinning: crawling }" />
            {{ crawling ? '本轮采集中' : '立即手动采集一次' }}
          </button>
        </section>
      </div>

      <section class="panel matches-panel" aria-labelledby="matches-title">
        <div class="panel-header matches-heading">
          <div>
            <h2 id="matches-title">比赛记录</h2>
          </div>
          <div class="segmented-control" aria-label="比赛记录状态">
            <button type="button" :class="{ active: matchTab === 'approved' }" @click="switchTab('approved')">
              已纳入 <span>{{ currentSeason?.approved_count || 0 }}</span>
            </button>
            <button type="button" :class="{ active: matchTab === 'rejected' }" @click="switchTab('rejected')">
              已剔除 <span>{{ currentSeason?.rejected_count || 0 }}</span>
            </button>
          </div>
        </div>

        <div class="data-toolbar match-toolbar">
          <label class="select-field compact" for="match-day-filter">
            <AppIcon name="calendar" />
            <select id="match-day-filter" v-model="dayFilter">
              <option value="">全部比赛日</option>
              <option v-for="d in matchDays" :key="d" :value="d">{{ d }}</option>
            </select>
          </label>
          <span class="toolbar-summary">显示 {{ visibleMatches.length }} / {{ matches.length }} 场</span>
          <span class="toolbar-spacer"></span>
          <button class="icon-button" type="button" aria-label="刷新比赛记录" title="刷新" :disabled="matchLoading" @click="loadMatches">
            <AppIcon name="refresh" :class="{ spinning: matchLoading }" />
          </button>
        </div>

        <div v-if="checked.length" class="selection-bar" role="status">
          <span><strong>{{ checked.length }}</strong> 场比赛已选中</span>
          <button
            class="button small"
            :class="matchTab === 'approved' ? 'danger' : 'primary'"
            type="button"
            :disabled="matchBusy"
            @click="bulk"
          >
            <AppIcon :name="matchTab === 'approved' ? 'archive' : 'check'" />
            {{ matchTab === 'approved' ? '剔除选中比赛' : '恢复选中比赛' }}
          </button>
        </div>

        <div class="table-scroll">
          <table class="data-table match-table">
            <thead>
              <tr>
                <th class="check-cell"><input type="checkbox" :checked="allMatchesSelected" aria-label="选择当前筛选的全部比赛" @change="toggleAll"></th>
                <th>比赛时间</th><th>地图</th><th>比分 / 对阵</th><th>名单命中</th><th>玩家</th><th class="action-cell"><span class="sr-only">操作</span></th>
              </tr>
            </thead>
            <tbody v-if="!matchLoading && visibleMatches.length">
              <tr
                v-for="m in visibleMatches"
                :key="m.match_id"
                class="match-row"
                :class="{ selected: checked.includes(m.match_id) }"
                title="查看比赛详情"
                @click="openMatch(m)"
              >
                <td class="check-cell" @click.stop>
                  <input v-model="checked" type="checkbox" :value="m.match_id" :aria-label="`选择比赛 ${m.match_id}`">
                </td>
                <td class="match-time-cell">
                  <strong class="mono-data">{{ formatPlayDay(m.play_day) }}</strong>
                  <small>{{ formatClock(m.start_time) }}</small>
                  <code>{{ m.match_id }}</code>
                </td>
                <td><strong>{{ m.map_name || '未知地图' }}</strong><small>{{ m.game_mode || '—' }}</small></td>
                <td>
                  <div class="score-cell">
                    <span>{{ m.team1_name || '队伍 A' }}</span>
                    <strong>{{ m.team1_score ?? '—' }} : {{ m.team2_score ?? '—' }}</strong>
                    <span>{{ m.team2_name || '队伍 B' }}</span>
                  </div>
                </td>
                <td><span class="hit-count"><strong>{{ m.roster_hit_count || 0 }}</strong> 人</span></td>
                <td><div class="player-chip-list"><span v-for="p in m.players" :key="p.player_id" :class="{ in: p.in_library }">{{ p.nickname }}</span></div></td>
                <td class="action-cell" @click.stop>
                  <div class="row-actions">
                    <button class="button text-button small" type="button" :aria-label="`查看 ${m.map_name || m.match_id} 详情`" @click="openMatch(m)">详情</button>
                    <button
                      class="button small"
                      :class="matchTab === 'approved' ? 'danger-ghost' : 'text-button'"
                      type="button"
                      :disabled="matchBusy"
                      @click="act(matchTab === 'approved' ? 'reject' : 'approve', [m.match_id])"
                    >{{ matchTab === 'approved' ? '剔除' : '恢复' }}</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="matchLoading" class="loading-state"><span class="loader"></span><p>正在加载比赛记录…</p></div>
        <div v-else-if="!visibleMatches.length" class="empty-state compact">
          <span><AppIcon name="database" :size="24" /></span>
          <h3>{{ matchTab === 'approved' ? '暂无已纳入比赛' : '暂无已剔除比赛' }}</h3>
          <p>{{ matchTab === 'approved' ? '完成采集后，符合条件的比赛会显示在这里。' : '被人工剔除的比赛会保留在这里，可随时恢复。' }}</p>
        </div>
      </section>
        </template>

        <section v-else-if="!seasonLoading" class="panel onboarding-panel">
          <div class="onboarding-mark"><AppIcon name="target" :size="42" /></div>
          <div><h2>建立第一个杯赛工作流</h2><p>创建杯赛后，即可继续配置种子名单、执行采集和审核比赛记录。</p></div>
          <button class="button primary" type="button" @click="createSeason"><AppIcon name="plus" />新建杯赛</button>
        </section>
      </main>
    </div>

    <AppModal
      :open="matchDetailOpen"
      :title="matchDetailTitle"
      eyebrow="MATCH REPORT"
      :description="matchDetailSubtitle"
      size="wide"
      @close="closeMatch"
    >
      <div v-if="matchDetail" class="match-detail">
        <section
          class="match-scoreboard"
          :style="matchDetail.map_url ? { '--map-image': `url(${matchDetail.map_url})` } : {}"
        >
          <div class="scoreboard-meta">
            <span>{{ matchDetail.map_name_en || matchDetail.game_mode || 'MATCH' }}</span>
            <span class="status-badge" :class="matchDetail.status === 'approved' ? 'success' : 'neutral'">
              <span class="status-dot"></span>{{ matchDetail.status === 'approved' ? '已纳入' : '已剔除' }}
            </span>
          </div>
          <div class="scoreboard-line">
            <div class="scoreboard-team">
              <span>{{ matchDetail.team1_name || '队伍 A' }}</span>
              <small v-if="Number(matchDetail.win_team) === 1">胜方</small>
            </div>
            <strong class="scoreboard-score">{{ matchDetail.team1_score ?? '—' }} : {{ matchDetail.team2_score ?? '—' }}</strong>
            <div class="scoreboard-team away">
              <span>{{ matchDetail.team2_name || '队伍 B' }}</span>
              <small v-if="Number(matchDetail.win_team) === 2">胜方</small>
            </div>
          </div>
          <p class="scoreboard-footnote">
            {{ matchDetail.map_name || '未知地图' }} · {{ matchDetail.game_mode || '未知模式' }}
            <template v-if="matchDetail.team1_half_score != null || matchDetail.team2_half_score != null">
              · 半场 {{ matchDetail.team1_half_score ?? '—' }}:{{ matchDetail.team2_half_score ?? '—' }}
            </template>
            <template v-if="matchDetail.team1_extra_score || matchDetail.team2_extra_score">
              · 加时 {{ matchDetail.team1_extra_score ?? 0 }}:{{ matchDetail.team2_extra_score ?? 0 }}
            </template>
          </p>
        </section>

        <div class="match-detail-facts">
          <div><span>比赛日</span><strong>{{ formatPlayDay(matchDetail.play_day) }}</strong></div>
          <div><span>开赛时间</span><strong>{{ formatDateTime(matchDetail.start_time) }}</strong></div>
          <div><span>时长</span><strong>{{ formatDuration(matchDetail.duration) }}</strong></div>
          <div><span>库内命中</span><strong>{{ matchDetail.roster_hit_count || 0 }} / {{ (matchDetail.players || []).length || '—' }}</strong></div>
        </div>

        <div v-if="matchDetailLoading" class="loading-state compact"><span class="loader"></span><p>正在读取选手数据…</p></div>
        <div v-else-if="matchDetailError" class="inline-alert error" role="alert">
          <AppIcon name="alert" />
          <span><strong>无法读取比赛详情</strong>{{ matchDetailError }}</span>
        </div>
        <template v-else>
          <section v-for="board in matchTeamBoards" :key="board.team" class="team-board" :class="{ winner: board.winner }">
            <div class="team-board-header">
              <div>
                <h3>{{ board.name }}</h3>
                <small>{{ board.players.length }} 名选手{{ board.winner ? ' · 胜方' : '' }}</small>
              </div>
              <strong>{{ board.score ?? '—' }}</strong>
            </div>
            <div class="table-scroll">
              <table class="data-table scoreboard-table">
                <thead>
                  <tr>
                    <th>选手</th>
                    <th class="num">K</th>
                    <th class="num">D</th>
                    <th class="num">A</th>
                    <th class="num">+/-</th>
                    <th class="num">ADR</th>
                    <th class="num">Rating</th>
                    <th class="num">KAST</th>
                    <th class="num">HS%</th>
                    <th class="num">FK</th>
                    <th>MVP</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="p in board.players" :key="p.player_id" :class="{ mvp: p.mvp }">
                    <td>
                      <div class="identity-cell">
                        <img v-if="p.avatar" class="player-monogram small match-avatar" :src="avatarUrl(p.avatar)" :alt="`${playerName(p)} 头像`">
                        <span v-else class="player-monogram small">{{ playerName(p).slice(0, 1).toUpperCase() }}</span>
                        <span>
                          <strong>{{ playerName(p) }}</strong>
                          <small>
                            <span v-if="p.in_library" class="lib-mark">库内</span>
                            <code>{{ p.player_id }}</code>
                          </small>
                        </span>
                      </div>
                    </td>
                    <td class="num">{{ p.kill ?? 0 }}</td>
                    <td class="num">{{ p.death ?? 0 }}</td>
                    <td class="num">{{ p.assist ?? 0 }}</td>
                    <td class="num" :class="diffClass(p)">{{ formatDiff(p) }}</td>
                    <td class="num">{{ formatStat(p.adpr, 0) }}</td>
                    <td class="num rating-cell">{{ formatStat(p.pw_rating || p.rating, 2) }}</td>
                    <td class="num">{{ formatRatio(p.kast) }}</td>
                    <td class="num">{{ formatRatio(p.headshot_ratio) }}</td>
                    <td class="num">{{ p.entry_kill ?? 0 }}</td>
                    <td>{{ p.mvp ? 'MVP' : '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>

        <div class="form-actions match-detail-actions">
          <button
            class="button small"
            :class="matchDetail.status === 'approved' ? 'danger-ghost' : 'primary'"
            type="button"
            :disabled="matchBusy || !matchDetail.match_id"
            @click="actFromDetail"
          >
            <AppIcon :name="matchDetail.status === 'approved' ? 'archive' : 'check'" />
            {{ matchDetail.status === 'approved' ? '剔除这场比赛' : '恢复这场比赛' }}
          </button>
        </div>
      </div>
    </AppModal>

    <AppModal
      :open="seasonModalOpen"
      :title="editingExisting ? '编辑杯赛' : '新建杯赛'"
      :eyebrow="editingExisting ? 'EDIT TOURNAMENT' : 'NEW TOURNAMENT'"
      description="设置公开标识、统计时间范围与比赛纳入规则。"
      size="large"
      :persistent="savingSeason || deletingSeason"
      @close="closeSeasonModal"
    >
      <form class="stack-form" @submit.prevent="saveSeason">
        <div class="field-grid two">
          <div class="field-group">
            <label for="season-cup">URL 标识 <span aria-hidden="true">*</span></label>
            <input id="season-cup" ref="cupInput" v-model.trim="form.cup" required autofocus placeholder="如 shark-s2" :disabled="editingExisting">
            <small>推荐英文 slug，用于公开页 URL。</small>
          </div>
          <div class="field-group">
            <label for="season-alias">展示名称</label>
            <input id="season-alias" v-model.trim="form.alias" placeholder="如 鲨鱼杯 S2">
          </div>
        </div>
        <div class="field-grid two">
          <div class="field-group">
            <label for="season-type">比赛类型</label>
            <select id="season-type" v-model="form.type">
              <option value="custom">自定义比赛</option>
              <option value="official">官方比赛</option>
            </select>
          </div>
          <div class="field-group">
            <label for="season-status">公开状态</label>
            <select id="season-status" v-model="form.status">
              <option value="active">进行中</option>
              <option value="archived">已归档</option>
            </select>
          </div>
        </div>
        <div class="field-grid two">
          <div class="field-group">
            <label for="season-start">开始时间</label>
            <input id="season-start" v-model="form.start" type="datetime-local" step="1" required>
            <small>Asia/Shanghai · 精确到秒</small>
          </div>
          <div class="field-group">
            <label for="season-end">结束时间</label>
            <input id="season-end" v-model="form.end" type="datetime-local" step="1" required>
            <small>结束时间包含该秒</small>
          </div>
        </div>
        <div class="field-group threshold-field">
          <div class="label-line">
            <label for="season-hit">库内占比门槛</label>
            <output for="season-hit">{{ form.hit }}%</output>
          </div>
          <input id="season-hit" v-model.number="form.hit" type="range" min="0" max="100" step="5">
          <div class="range-labels"><span>宽松 0%</span><span>严格 100%</span></div>
        </div>
        <label class="field-group checkbox-field" for="season-champion">
          <span><input id="season-champion" v-model="form.championEnabled" type="checkbox"> 计算冠军和亚军</span>
          <small>关闭后仍采集并展示比赛、选手数据与排名，不运行冠军判断任务。</small>
        </label>
        <div class="form-actions">
          <button
            v-if="editingExisting"
            class="button danger-ghost season-delete-button"
            type="button"
            :disabled="savingSeason || deletingSeason"
            @click="deleteSeason"
          >
            <span v-if="deletingSeason" class="button-spinner dark"></span>
            <AppIcon v-else name="trash" />
            {{ deletingSeason ? '删除中…' : '删除杯赛' }}
          </button>
          <button class="button subtle" type="button" :disabled="savingSeason || deletingSeason" @click="closeSeasonModal">取消</button>
          <button class="button primary" type="submit" :disabled="savingSeason || deletingSeason">
            <span v-if="savingSeason" class="button-spinner"></span>
            <AppIcon v-else name="save" />
            {{ savingSeason ? '保存中…' : '保存杯赛' }}
          </button>
        </div>
      </form>
    </AppModal>

    <div v-if="toast.message" class="toast" :class="toast.type" :role="toast.type === 'error' ? 'alert' : 'status'">
      <AppIcon :name="toast.type === 'error' ? 'alert' : 'check'" />{{ toast.message }}
    </div>
  </AdminLayout>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api, avatarUrl } from '../api'
import AdminLayout from '../components/AdminLayout.vue'
import AppIcon from '../components/AppIcon.vue'
import AppModal from '../components/AppModal.vue'

const seasons = ref([])
const currentCup = ref('')
const library = ref([])
const seedQ = ref('')
const seedChecked = ref([])
const rosterRaw = ref('')
const form = ref(defaultForm())
const crawlMsg = ref('选择杯赛后可执行采集')
const crawling = ref(false)
const autoEnabled = ref(false)
const matchTab = ref('approved')
const matches = ref([])
const dayFilter = ref('')
const checked = ref([])
const toast = ref({ message: '', type: 'success' })
const seasonLoading = ref(false)
const savingSeason = ref(false)
const deletingSeason = ref(false)
const seasonModalOpen = ref(false)
const savingRoster = ref(false)
const matchLoading = ref(false)
const matchBusy = ref(false)
const cupInput = ref(null)
const matchDetailOpen = ref(false)
const matchDetail = ref(null)
const matchDetailLoading = ref(false)
const matchDetailError = ref('')
let crawlTimer
let toastTimer

function defaultForm() { return { cup: '', alias: '', type: 'custom', start: '', end: '', hit: 60, status: 'active', championEnabled: false } }
const currentSeason = computed(() => seasons.value.find((s) => s.cup_name === currentCup.value))
const seasonExpired = computed(() => {
  const end = currentSeason.value?.end_date
  return Boolean(end && Date.now() > new Date(end).getTime())
})
const crawlStateLabel = computed(() => {
  if (!currentCup.value) return '未选择'
  if (seasonExpired.value) return '已截止'
  if (crawling.value) return '本轮运行中'
  return autoEnabled.value ? '已启动' : '未启动'
})
const crawlHeadline = computed(() => {
  if (seasonExpired.value) return '赛季采集已截止'
  if (crawling.value) return '正在扫描比赛数据'
  if (autoEnabled.value) return '自动采集正在运行'
  return '等待启动自动采集'
})
const crawlButtonDisabled = computed(() => (
  crawling.value || autoEnabled.value || seasonExpired.value || currentSeason.value?.status !== 'active'
))
const manualCrawlDisabled = computed(() => (
  crawling.value || !currentSeason.value
))
const crawlButtonLabel = computed(() => {
  if (seasonExpired.value) return '赛季已截止'
  if (crawling.value) return '本轮采集中'
  if (autoEnabled.value) return '自动采集已启动'
  if (currentSeason.value?.status !== 'active') return '赛季已归档'
  return '启动自动采集'
})
const editingExisting = computed(() => seasons.value.some((s) => s.cup_name === form.value.cup))
const activeSeasons = computed(() => seasons.value.filter((s) => s.status === 'active').length)
const totalApproved = computed(() => seasons.value.reduce((sum, s) => sum + Number(s.approved_count || 0), 0))
const totalRejected = computed(() => seasons.value.reduce((sum, s) => sum + Number(s.rejected_count || 0), 0))
const filteredLibrary = computed(() => {
  const query = seedQ.value.toLowerCase().trim()
  return library.value.filter((p) => !query || `${p.player_id}${p.nickname || ''}${p.alias_name || ''}`.toLowerCase().includes(query))
})
const matchDays = computed(() => [...new Set(matches.value.map((m) => m.play_day).filter(Boolean))].sort().reverse())
const visibleMatches = computed(() => matches.value.filter((m) => !dayFilter.value || m.play_day === dayFilter.value))
const allMatchesSelected = computed(() => visibleMatches.value.length > 0 && visibleMatches.value.every((m) => checked.value.includes(m.match_id)))
const matchDetailTitle = computed(() => matchDetail.value?.map_name || '比赛详情')
const matchDetailSubtitle = computed(() => {
  if (!matchDetail.value) return '查看双方选手的当场数据。'
  const day = formatPlayDay(matchDetail.value.play_day)
  return [day !== '—' ? day : '', matchDetail.value.match_id].filter(Boolean).join(' · ')
})
const matchTeamBoards = computed(() => {
  const match = matchDetail.value
  if (!match) return []
  const grouped = { 1: [], 2: [], other: [] }
  for (const player of match.players || []) {
    const team = Number(player.team)
    if (team === 1 || team === 2) grouped[team].push(player)
    else grouped.other.push(player)
  }
  const sortPlayers = (list) => [...list].sort((a, b) => (Number(b.pw_rating || b.rating) || 0) - (Number(a.pw_rating || a.rating) || 0))
  const boards = [
    { team: 1, name: match.team1_name || '队伍 A', score: match.team1_score, winner: Number(match.win_team) === 1, players: sortPlayers(grouped[1]) },
    { team: 2, name: match.team2_name || '队伍 B', score: match.team2_score, winner: Number(match.win_team) === 2, players: sortPlayers(grouped[2]) },
  ]
  if (grouped.other.length) {
    boards.push({ team: 0, name: '未分队', score: null, winner: false, players: sortPlayers(grouped.other) })
  }
  return boards.filter((board) => board.players.length)
})

function displaySeason(s) { return s.cup_alias || s.name || s.cup_name }
function displayPlayer(p) { return p.alias_name || p.nickname || p.player_id }
function padIndex(index) { return String(index).padStart(2, '0') }
function pct(value) {
  const number = Number(value)
  if (Number.isNaN(number)) return 60
  return number <= 1 ? Math.round(number * 100) : Math.round(number)
}
function toDateTimeInput(value) {
  if (!value) return ''
  return String(value).replace(' ', 'T').slice(0, 19)
}
function formatDateTime(value) {
  return value ? String(value).replace('T', ' ').slice(0, 19) : '…'
}
function formatClock(value) {
  if (!value) return '时间未知'
  const text = String(value).replace('T', ' ')
  const time = text.match(/\b(\d{2}:\d{2}(?::\d{2})?)/)?.[1]
  if (time) return time.length === 5 ? `${time}:00` : time
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleTimeString('zh-CN', { hour12: false })
}
function formatRange(season) {
  if (!season || (!season.start_date && !season.end_date)) return '未设置时间段'
  return `${formatDateTime(season.start_date)} — ${formatDateTime(season.end_date)}`
}
function formatPlayDay(value) {
  const raw = String(value || '').replace(/\D/g, '')
  if (raw.length === 8) return `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`
  return value || '—'
}
function formatDuration(value) {
  const number = Number(value)
  if (!Number.isFinite(number) || number <= 0) return '—'
  if (number < 180) return `${Math.round(number)} 分钟`
  const total = Math.round(number)
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  if (hours) return `${hours} 小时 ${minutes} 分钟`
  return `${minutes} 分钟`
}
function playerName(player) {
  return player?.alias_name || player?.nickname || player?.player_id || '未知选手'
}
function formatStat(value, digits = 0) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  return number.toFixed(digits)
}
function formatRatio(value) {
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  const percent = number <= 1 ? number * 100 : number
  return `${Math.round(percent)}%`
}
function formatDiff(player) {
  const diff = Number(player?.kill || 0) - Number(player?.death || 0)
  return diff > 0 ? `+${diff}` : String(diff)
}
function diffClass(player) {
  const diff = Number(player?.kill || 0) - Number(player?.death || 0)
  if (diff > 0) return 'positive'
  if (diff < 0) return 'negative'
  return ''
}
function show(message, type = 'success') {
  clearTimeout(toastTimer)
  toast.value = { message, type }
  toastTimer = setTimeout(() => { toast.value.message = '' }, 3200)
}
function resetForm() { form.value = defaultForm() }
function closeSeasonModal() {
  if (savingSeason.value || deletingSeason.value) return
  seasonModalOpen.value = false
  resetForm()
}
async function createSeason() {
  resetForm()
  seasonModalOpen.value = true
  await nextTick()
  cupInput.value?.focus()
}
function editSeason(s) {
  form.value = {
    cup: s.cup_name,
    alias: s.cup_alias || s.name || '',
    type: s.match_type || 'custom',
    start: toDateTimeInput(s.start_date),
    end: toDateTimeInput(s.end_date),
    hit: pct(s.hit_ratio),
    status: s.status || 'active',
    championEnabled: Boolean(s.champion_enabled),
  }
  seasonModalOpen.value = true
}
async function loadSeasons() {
  seasonLoading.value = true
  try {
    const data = await api.get('/api/admin/season/list')
    seasons.value = data.seasons || []
    if (currentSeason.value) applyCrawl(currentSeason.value.crawl || {})
  } catch (e) {
    show(e.message, 'error')
  } finally {
    seasonLoading.value = false
  }
}
async function selectCup(cup) {
  currentCup.value = cup
  checked.value = []
  dayFilter.value = ''
  closeMatch()
  await Promise.all([loadRoster(), loadLibrary(), loadMatches(), refreshCrawl()])
}
async function saveSeason() {
  if (!form.value.cup.trim()) return show('请填写 URL 标识', 'error')
  savingSeason.value = true
  try {
    const data = await api.send('/api/admin/season/save', {
      cup: form.value.cup.trim(),
      cup_alias: form.value.alias,
      match_type: form.value.type,
      start_date: form.value.start,
      end_date: form.value.end,
      status: form.value.status,
      hit_percent: String(form.value.hit ?? 60),
      champion_enabled: form.value.championEnabled ? '1' : '0',
    })
    show(typeof data === 'string' ? data : '杯赛已保存')
    const cup = form.value.cup.trim()
    await loadSeasons()
    await selectCup(cup)
    seasonModalOpen.value = false
    resetForm()
  } catch (e) {
    show(e.message, 'error')
  } finally {
    savingSeason.value = false
  }
}
async function deleteSeason() {
  const cup = form.value.cup.trim()
  const season = seasons.value.find((item) => item.cup_name === cup)
  if (!season) return show('赛季不存在或已被删除', 'error')
  const name = displaySeason(season)
  const confirmed = window.confirm(
    `确认删除「${name}」？\n\n赛季配置、种子名单、比赛纳入记录、称号和冠军结果将被移除。原始比赛数据会保留但解除赛季关联。此操作无法撤销。`,
  )
  if (!confirmed) return

  deletingSeason.value = true
  try {
    const data = await api.post('/api/admin/season/delete', { cup })
    const deletedCurrent = currentCup.value === cup
    seasonModalOpen.value = false
    resetForm()
    if (deletedCurrent) {
      currentCup.value = ''
      checked.value = []
      matches.value = []
      seedChecked.value = []
      rosterRaw.value = ''
      closeMatch()
      if (crawlTimer) {
        clearInterval(crawlTimer)
        crawlTimer = null
      }
      applyCrawl({ state: 'idle', message: '选择杯赛后可执行采集' })
    }
    await loadSeasons()
    if (deletedCurrent && seasons.value.length) await selectCup(seasons.value[0].cup_name)
    show(data?.message || '赛季已删除')
  } catch (e) {
    show(e.message, 'error')
  } finally {
    deletingSeason.value = false
  }
}
async function loadLibrary() {
  try {
    const data = await api.get('/api/admin/players?in_library=1')
    library.value = data.players || []
  } catch (e) { show(e.message, 'error') }
}
async function loadRoster() {
  if (!currentCup.value) return
  try {
    const data = await api.get('/api/admin/season/roster/get?cup=' + encodeURIComponent(currentCup.value))
    const roster = data.roster || []
    seedChecked.value = roster.map((r) => r.player_id)
    rosterRaw.value = roster.map((r) => r.player_id).join(', ')
  } catch (e) { show(e.message, 'error') }
}
async function saveRoster() {
  if (!currentCup.value) return show('请先选择杯赛', 'error')
  savingRoster.value = true
  try {
    const data = await api.send('/api/admin/season/roster/save', { cup: currentCup.value, player_ids: rosterRaw.value })
    show(typeof data === 'string' ? data : '种子名单已保存')
    await Promise.all([loadRoster(), loadSeasons()])
  } catch (e) {
    show(e.message, 'error')
  } finally {
    savingRoster.value = false
  }
}
function applyCrawl(status) {
  crawling.value = Boolean(status.running || status.state === 'running')
  autoEnabled.value = Boolean(status.auto_enabled)
  crawlMsg.value = status.message || (autoEnabled.value
    ? '已启动，每 10 分钟自动获取一次，赛季截止后停止。'
    : '点击一次启动，之后无需手动重复采集。')
}
async function refreshCrawl() {
  if (!currentCup.value) return
  try {
    const wasRunning = crawling.value
    const wasEnabled = autoEnabled.value
    const status = await api.get('/api/admin/season/crawl/status?cup=' + encodeURIComponent(currentCup.value))
    applyCrawl(status)
    if ((crawling.value || autoEnabled.value) && !crawlTimer) crawlTimer = setInterval(refreshCrawl, 15000)
    if (!crawling.value && !autoEnabled.value && crawlTimer) {
      clearInterval(crawlTimer)
      crawlTimer = null
    }
    if ((wasRunning && !crawling.value) || (wasEnabled && !autoEnabled.value)) {
      await Promise.all([loadMatches(), loadSeasons()])
    }
  } catch (e) { show(e.message, 'error') }
}
async function startCrawl(mode = 'auto') {
  if (!currentCup.value || (mode === 'auto' ? crawlButtonDisabled.value : manualCrawlDisabled.value)) return
  try {
    const data = await api.get('/api/admin/season/crawl?cup=' + encodeURIComponent(currentCup.value) + '&mode=' + mode)
    show(typeof data === 'string' ? data : mode === 'once' ? '手动采集已启动' : '自动采集已启动')
    await refreshCrawl()
  } catch (e) { show(e.message, 'error') }
}
function switchTab(tab) {
  matchTab.value = tab
  checked.value = []
  dayFilter.value = ''
  closeMatch()
  loadMatches()
}
async function openMatch(match) {
  if (!match?.match_id || !currentCup.value) return
  matchDetailOpen.value = true
  matchDetail.value = match
  matchDetailLoading.value = true
  matchDetailError.value = ''
  try {
    matchDetail.value = await api.get(`/api/admin/selection/detail?cup=${encodeURIComponent(currentCup.value)}&match_id=${encodeURIComponent(match.match_id)}`)
  } catch (e) {
    matchDetailError.value = e.message
  } finally {
    matchDetailLoading.value = false
  }
}
function closeMatch() {
  matchDetailOpen.value = false
  matchDetail.value = null
  matchDetailError.value = ''
  matchDetailLoading.value = false
}
async function actFromDetail() {
  const match = matchDetail.value
  if (!match?.match_id) return
  const ok = await act(match.status === 'approved' ? 'reject' : 'approve', [match.match_id])
  if (ok) closeMatch()
}
async function loadMatches() {
  if (!currentCup.value) return
  matchLoading.value = true
  try {
    const data = await api.get(`/api/admin/selection/list?cup=${encodeURIComponent(currentCup.value)}&status=${matchTab.value}`)
    matches.value = data.list || []
    checked.value = []
  } catch (e) {
    show(e.message, 'error')
  } finally {
    matchLoading.value = false
  }
}
function toggleAll(event) {
  const visibleIds = visibleMatches.value.map((m) => m.match_id)
  checked.value = event.target.checked
    ? [...new Set([...checked.value, ...visibleIds])]
    : checked.value.filter((id) => !visibleIds.includes(id))
}
async function act(type, ids) {
  matchBusy.value = true
  try {
    const data = await api.send(`/api/admin/selection/${type}`, { cup: currentCup.value, match_ids: ids.join(',') })
    show(typeof data === 'string' ? data : '比赛状态已更新')
    await Promise.all([loadMatches(), loadSeasons()])
    return true
  } catch (e) {
    show(e.message, 'error')
    return false
  } finally {
    matchBusy.value = false
  }
}
function bulk() {
  if (!checked.value.length) return show('请先选择比赛', 'error')
  return act(matchTab.value === 'approved' ? 'reject' : 'approve', checked.value)
}

watch(seedChecked, (ids) => {
  const extras = rosterRaw.value
    .split(/[,;\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((id) => !library.value.some((p) => p.player_id === id))
  rosterRaw.value = [...new Set([...extras, ...ids])].join(', ')
})

onMounted(async () => {
  await Promise.all([loadSeasons(), loadLibrary()])
  if (seasons.value.length) await selectCup(seasons.value[0].cup_name)
})
onBeforeUnmount(() => {
  if (crawlTimer) clearInterval(crawlTimer)
  clearTimeout(toastTimer)
})
</script>
