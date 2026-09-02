<template>
  <Transition name="compare-tray">
    <aside v-if="selected.length" class="compare-tray" aria-label="PLAYER 对比栏">
      <div class="compare-tray-inner">
        <div class="compare-tray-title">
          <span>{{ selected.length }} / {{ PLAYER_COMPARE_LIMIT }}</span>
          <strong>PLAYER 对比</strong>
        </div>
        <div class="compare-tray-players" aria-label="已选选手">
          <div v-for="(player, index) in selected" :key="player.player_id" class="compare-tray-player">
            <span class="compare-slot-index">P{{ index + 1 }}</span>
            <PlayerAvatar :src="player.avatar" :name="displayName(player)" />
            <strong>{{ displayName(player) }}</strong>
            <button type="button" :aria-label="`从对比中移除 ${displayName(player)}`" @click="remove(player.player_id)">
              <AppIcon name="x" :size="14" />
            </button>
          </div>
        </div>
        <div class="compare-tray-actions">
          <button class="button text-button" type="button" @click="clear">清空</button>
          <router-link v-if="selected.length >= PLAYER_COMPARE_MINIMUM" class="button primary" :to="targetRoute">
            开始对比<AppIcon name="arrowRight" :size="16" />
          </router-link>
          <button v-else class="button primary" type="button" disabled title="至少选择两名选手">再选 1 人</button>
        </div>
      </div>
    </aside>
  </Transition>
</template>

<script setup>
import { computed, toRef } from 'vue'
import AppIcon from './AppIcon.vue'
import PlayerAvatar from './PlayerAvatar.vue'
import {
  PLAYER_COMPARE_LIMIT,
  PLAYER_COMPARE_MINIMUM,
  compareRoute,
  usePlayerCompare,
} from '../playerCompare'

const props = defineProps({
  cup: { type: String, required: true },
  day: { type: String, default: '' },
})

const cup = toRef(props, 'cup')
const day = toRef(props, 'day')
const { selected, selectedIds, remove, clear } = usePlayerCompare(cup, day)
const targetRoute = computed(() => compareRoute(cup.value, day.value, selectedIds.value))

function displayName(player) {
  return player.alias_name || player.nickname || player.player_id || '选手'
}
</script>

