<script setup>
// Красный «!» у номера утверждённого плана: с утверждения его заявки сняли или появились
// новые — план стоит пересчитать. При наведении — кратко, по клику — подробно (show).
import { computed } from 'vue'

import { replanHint } from '../utils/replanHint.js'

const props = defineProps({
  summary: { type: Object, default: null },
  large: { type: Boolean, default: false }, // в заголовке открытого плана
})
defineEmits(['show'])

const hint = computed(() => replanHint(props.summary))
</script>

<template>
  <button
    v-if="hint"
    type="button"
    :class="['replan-mark', { large }]"
    :title="`${hint}. Нажмите — что не так`"
    :aria-label="hint"
    @click.stop="$emit('show')"
    @dblclick.stop
  >
    !
  </button>
</template>

<style scoped>
.replan-mark {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 16px;
  min-width: 0;
  height: 16px;
  margin-left: 6px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: #dc2626;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  vertical-align: middle;
  cursor: pointer;
}

.replan-mark:hover:not(:disabled) {
  background: #b91c1c;
  color: #fff;
  box-shadow: 0 0 0 3px rgb(220 38 38 / 20%);
}

.replan-mark.large {
  width: 22px;
  height: 22px;
  margin-left: 0;
  font-size: 14px;
}
</style>
