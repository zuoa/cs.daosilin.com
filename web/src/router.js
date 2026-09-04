import { createRouter, createWebHistory } from 'vue-router'
import { api } from './api'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./views/Home.vue') },
    { path: '/admin/login', component: () => import('./views/Login.vue'), meta: { title: '管理登录' } },
    { path: '/admin/season', component: () => import('./views/AdminSeason.vue'), meta: { admin: true, title: '杯赛与采集' } },
    { path: '/admin/players', component: () => import('./views/AdminPlayers.vue'), meta: { admin: true, title: '玩家库' } },
    { path: '/admin/tasks', component: () => import('./views/AdminTasks.vue'), meta: { admin: true, title: '任务中心' } },
    { path: '/admin/settings', component: () => import('./views/AdminSettings.vue'), meta: { admin: true, title: 'API 与安全' } },
    { path: '/draft', component: () => import('./views/Draft.vue'), meta: { title: '选人结果' } },
    { path: '/broadcast/:cup', component: () => import('./views/Broadcast.vue'), meta: { title: '赛事直播数据' } },
    { path: '/compare/:cup/:day?', component: () => import('./views/Compare.vue') },
    { path: '/player/:id/:cup?/:day?', component: () => import('./views/Player.vue') },
    { path: '/:cup/community', component: () => import('./views/CommunityShelves.vue'), meta: { title: '从夯到拉排名' } },
    { path: '/:cup/:day?', component: () => import('./views/Season.vue') },
  ],
  scrollBehavior() {
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
})

export default router
