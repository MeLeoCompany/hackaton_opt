<script setup>
// Окно или смена в строке таблицы, разложенные так же, как фильтр «чч:мм – чч:мм» в шапке:
// начало под левой половиной фильтра, тире под тире, конец под правой половиной.
import { computed } from 'vue'

import { moscowTimeRangeParts } from '../utils/moscowTime.js'

const props = defineProps({
  start: { type: String, required: true }, // ISO-время начала
  end: { type: String, required: true }, // ISO-время конца
})

const parts = computed(() => moscowTimeRangeParts(props.start, props.end))
</script>

<template>
  <div class="range-value">
    <span>{{ parts.start }}</span>
    <span class="range-dash">–</span>
    <span :title="parts.endsNextDay ? 'Заканчивается на следующие сутки' : ''">
      {{ parts.end }}<sup v-if="parts.endsNextDay">+1</sup>
    </span>
  </div>
</template>
