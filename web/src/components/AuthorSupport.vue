<template>
  <span
    ref="rootEl"
    class="author-support"
    @mouseenter="openFromHover"
    @mouseleave="closeFromHover"
    @focusin="openFromFocus"
    @focusout="closeFromFocus"
  >
    <span class="author-credit-label">
      Made with <span class="author-heart" aria-hidden="true">♥</span> by
    </span>
    <button
      ref="triggerEl"
      class="author-trigger"
      type="button"
      aria-label="查看 ZUOAJ 的作者信息与支持方式"
      aria-haspopup="dialog"
      :aria-expanded="isOpen"
      aria-controls="author-support-panel"
      @click.stop="togglePinned"
    >
      <span>ZUOAJ</span>
      <AppIcon name="chevronDown" :size="13" :class="{ rotated: isOpen }" />
    </button>

    <Transition name="author-popover">
      <section
        v-if="isOpen"
        id="author-support-panel"
        class="author-popover"
        role="dialog"
        aria-modal="false"
        aria-labelledby="author-support-title"
        @click.stop
      >
        <header class="author-popover-header">
          <div>
            <strong id="author-support-title">支持 ZUOAJ</strong>
            <span>谢谢你喜欢这个小站</span>
          </div>
          <button type="button" aria-label="关闭作者名片" @click="dismiss">
            <AppIcon name="x" :size="15" />
          </button>
        </header>

        <div class="author-code-grid">
          <figure>
            <div class="author-code-frame">
              <img :src="supportCode" width="635" height="593" alt="ZUOAJ 的赞赏码" />
            </div>
            <figcaption><strong>喝杯瑞幸</strong><span>微信扫码赞赏</span></figcaption>
          </figure>
          <figure>
            <div class="author-code-frame">
              <img :src="wechatCode" width="678" height="641" alt="ZUOAJ 的微信好友码" />
            </div>
            <figcaption><strong>加个好友</strong><span>微信扫码添加</span></figcaption>
          </figure>
        </div>
      </section>
    </Transition>
  </span>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import supportCode from '../assets/zuoaj-support.png'
import wechatCode from '../assets/zuoaj-wechat.png'
import AppIcon from './AppIcon.vue'

const rootEl = ref(null)
const triggerEl = ref(null)
const hovered = ref(false)
const focused = ref(false)
const pinned = ref(false)
const dismissed = ref(false)
const isOpen = computed(() => !dismissed.value && (hovered.value || focused.value || pinned.value))

function openFromHover() {
  hovered.value = true
  dismissed.value = false
}

function closeFromHover() {
  hovered.value = false
  if (!focused.value && !pinned.value) dismissed.value = false
}

function openFromFocus() {
  focused.value = true
  dismissed.value = false
}

function closeFromFocus(event) {
  if (rootEl.value?.contains(event.relatedTarget)) return
  focused.value = false
  if (!hovered.value && !pinned.value) dismissed.value = false
}

function togglePinned() {
  if (pinned.value) {
    pinned.value = false
    dismissed.value = true
    return
  }
  pinned.value = true
  dismissed.value = false
}

function dismiss() {
  triggerEl.value?.focus({ preventScroll: true })
  pinned.value = false
  dismissed.value = true
}

function handleDocumentPointerDown(event) {
  if (!rootEl.value?.contains(event.target)) {
    pinned.value = false
    dismissed.value = true
  }
}

function handleDocumentKeydown(event) {
  if (event.key === 'Escape' && isOpen.value) dismiss()
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown)
  document.addEventListener('keydown', handleDocumentKeydown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown)
  document.removeEventListener('keydown', handleDocumentKeydown)
})
</script>
