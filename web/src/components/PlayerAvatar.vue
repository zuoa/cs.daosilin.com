<template>
  <img
    v-if="showImage"
    :src="avatarUrl(src)"
    :alt="`${name || '选手'} 头像`"
    @error="failed = true"
  >
  <span v-else class="avatar-fallback fallback" :aria-label="`${name || '选手'} 头像占位`" role="img">
    {{ initial }}
  </span>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { avatarUrl } from '../api'

const props = defineProps({
  src: { type: String, default: '' },
  name: { type: String, default: '' },
})

const failed = ref(false)
const showImage = computed(() => Boolean(props.src) && !failed.value)
const initial = computed(() => (props.name || '?').trim().slice(0, 1).toUpperCase() || '?')

watch(() => props.src, () => { failed.value = false })
</script>
