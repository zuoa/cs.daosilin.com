import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import Season from './views/Season.vue'
import Player from './views/Player.vue'
import Login from './views/Login.vue'
import AdminSeason from './views/AdminSeason.vue'
import AdminPlayers from './views/AdminPlayers.vue'
import { api } from './api'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/admin/login', component: Login },
    { path: '/admin/season', component: AdminSeason, meta: { admin: true } },
    { path: '/admin/players', component: AdminPlayers, meta: { admin: true } },
    { path: '/player/:id/:cup?/:day?', component: Player },
    { path: '/:cup/:day?', component: Season },
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

export default router
