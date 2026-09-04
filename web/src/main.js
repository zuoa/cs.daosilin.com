import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import './style.css'
import './player-compare.css'
import './broadcast.css'

if (window.location.pathname.startsWith('/broadcast/')) {
  document.documentElement.classList.add('broadcast-document')
}

createApp(App).use(router).mount('#app')
