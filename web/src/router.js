import { createRouter, createWebHistory } from 'vue-router'
import { api } from './api'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./views/Home.vue'), meta: { title: 'CS2 赛事数据、选手 Rating 与战绩' } },
    { path: '/admin/login', component: () => import('./views/Login.vue'), meta: { title: '管理登录', noindex: true } },
    { path: '/admin/season', component: () => import('./views/AdminSeason.vue'), meta: { admin: true, title: '杯赛与采集', noindex: true } },
    { path: '/admin/drafts', component: () => import('./views/AdminDrafts.vue'), meta: { admin: true, title: '选人记录', noindex: true } },
    { path: '/admin/players', component: () => import('./views/AdminPlayers.vue'), meta: { admin: true, title: '玩家库', noindex: true } },
    { path: '/admin/honours', component: () => import('./views/AdminHonours.vue'), meta: { admin: true, title: '荣誉奖项', noindex: true } },
    { path: '/admin/tasks', component: () => import('./views/AdminTasks.vue'), meta: { admin: true, title: '任务中心', noindex: true } },
    { path: '/admin/feedback', component: () => import('./views/AdminFeedback.vue'), meta: { admin: true, title: '反馈收件箱', noindex: true } },
    { path: '/admin/settings', component: () => import('./views/AdminSettings.vue'), meta: { admin: true, title: 'API 与安全', noindex: true } },
    { path: '/draft', component: () => import('./views/Draft.vue'), meta: { title: '选人结果', noindex: true } },
    { path: '/broadcast/:cup', component: () => import('./views/Broadcast.vue'), meta: { title: '赛事直播数据', noindex: true } },
    { path: '/compare/:cup/:day?', component: () => import('./views/Compare.vue'), meta: { noindex: true } },
    { path: '/player/:id/:cup?/:day?', component: () => import('./views/Player.vue') },
    { path: '/:cup/community', component: () => import('./views/CommunityShelves.vue'), meta: { title: '从夯到拉排名' } },
    { path: '/:cup/honours', component: () => import('./views/Honours.vue'), meta: { title: '赛季荣誉展' } },
    { path: '/:cup/:day?', component: () => import('./views/Season.vue') },
  ],
  scrollBehavior(to) {
    if (to.hash) return { el: to.hash, top: 20, behavior: 'smooth' }
    return { top: 0 }
  },
})

router.beforeEach(async (to) => {
  if (!to.meta.admin) return true
  try {
    await api.me()
    return true
  } catch {
    return { path: '/admin/login', query: { next: to.fullPath } }
  }
})

router.afterEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 熊掌CS Major` : '熊掌CS Major'
  const robots = document.querySelector('meta[name="robots"]')
  if (robots) robots.setAttribute('content', to.meta.noindex ? 'noindex,follow' : 'index,follow')
  const canonical = document.querySelector('link[rel="canonical"]')
  if (canonical) canonical.setAttribute('href', new URL(to.path, window.location.origin).href)
})

export default router
