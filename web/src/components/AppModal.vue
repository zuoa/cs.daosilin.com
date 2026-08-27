<template>
  <Teleport to="body">
    <Transition name="modal-fade">
      <div v-if="open" class="modal-backdrop" @mousedown.self="requestClose">
        <section
          ref="modalEl"
          class="app-modal"
          :class="size"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="titleId"
        >
          <header class="modal-header">
            <div>
              <h2 :id="titleId">{{ title }}</h2>
              <p v-if="description">{{ description }}</p>
            </div>
            <button class="icon-button" type="button" :aria-label="closeLabel" :title="closeLabel" @click="requestClose">
              <AppIcon name="x" />
            </button>
          </header>
          <div class="modal-content"><slot /></div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'

const props = defineProps({
  open: { type: Boolean, default: false },
  title: { type: String, required: true },
  eyebrow: { type: String, default: '' },
  description: { type: String, default: '' },
  size: { type: String, default: 'medium' },
  closeLabel: { type: String, default: '关闭弹窗' },
  persistent: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])
const modalEl = ref(null)
const titleId = `modal-title-${Math.random().toString(36).slice(2, 9)}`
let previousOverflow = ''
let previousFocus = null

function requestClose() {
  if (!props.persistent) emit('close')
}
function focusables() {
  return [...(modalEl.value?.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex]:not([tabindex="-1"])') || [])]
}
function handleKeydown(event) {
  if (event.key === 'Escape') {
    event.preventDefault()
    requestClose()
    return
  }
  if (event.key !== 'Tab') return
  const items = focusables()
  if (!items.length) return
  const first = items[0]
  const last = items[items.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => props.open, async (isOpen) => {
  if (isOpen) {
    previousFocus = document.activeElement
    previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', handleKeydown)
    await nextTick()
    const preferred = modalEl.value?.querySelector('[autofocus]')
    ;(preferred || focusables()[0] || modalEl.value)?.focus()
  } else {
    document.removeEventListener('keydown', handleKeydown)
    document.body.style.overflow = previousOverflow
    previousFocus?.focus?.()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.body.style.overflow = previousOverflow
})
</script>
