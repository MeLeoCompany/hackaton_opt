<script setup>
// Поле времени: набирается руками, неверные цифры просто не вводятся.
// Маска не даёт получить «18:90» — час больше 23 и минуты больше 59 набрать нельзя.
// По клику открывается список получасовых значений (как часики у Яндекса), он же фильтруется
// по набранному: «9» оставит 09:00 и 09:30.
import { computed, nextTick, ref, watch } from 'vue'

import { completeTime, maskTimeInput } from '../utils/moscowTime.js'

const props = defineProps({
  modelValue: { type: String, default: '' },
  ariaLabel: { type: String, default: 'время' },
})
const emit = defineEmits(['update:modelValue'])

const STEP_MINUTES = 30
const DROPDOWN_MIN_WIDTH = 72
const SUGGESTIONS = Array.from({ length: (24 * 60) / STEP_MINUTES }, (_, index) => {
  const minutes = index * STEP_MINUTES
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
})

const input = ref(null)
const text = ref(props.modelValue)
const open = ref(false)
const dropdownStyle = ref({})

watch(
  () => props.modelValue,
  (value) => {
    if (value !== text.value) text.value = value
  },
)

const suggestions = computed(() => {
  const typed = text.value.replace(':', '')
  if (!typed) return SUGGESTIONS
  const matching = SUGGESTIONS.filter((time) => time.replace(':', '').startsWith(typed))
  return matching.length ? matching : SUGGESTIONS
})

function onInput(event) {
  text.value = maskTimeInput(event.target.value)
  event.target.value = text.value
  open.value = true
  // время набрано целиком — отдаём сразу, не дожидаясь ухода из поля: фильтр и предпросмотр
  // синхронизации обновляются по ходу набора
  if (/^\d\d:\d\d$/.test(text.value)) emit('update:modelValue', text.value)
}

async function openDropdown() {
  const box = input.value.getBoundingClientRect()
  // список висит поверх прокручиваемой таблицы, поэтому позиция фиксированная
  // поле бывает уже самого списка (узкий фильтр «чч:мм – чч:мм») — список не уже, чем нужно под «00:00»
  const width = Math.max(box.width, DROPDOWN_MIN_WIDTH)
  dropdownStyle.value = { top: `${box.bottom + 2}px`, left: `${box.left}px`, width: `${width}px` }
  open.value = true
  await nextTick()
  document.querySelector('.time-dropdown .current')?.scrollIntoView({ block: 'center' })
}

function choose(time) {
  text.value = time
  open.value = false
  emit('update:modelValue', time)
}

function finish() {
  open.value = false
  const value = completeTime(text.value)
  text.value = value
  emit('update:modelValue', value)
}
</script>

<template>
  <input
    ref="input"
    :value="text"
    class="time-input"
    :aria-label="ariaLabel"
    inputmode="numeric"
    maxlength="5"
    placeholder="чч:мм"
    @input="onInput"
    @focus="openDropdown"
    @blur="finish"
    @keyup.enter="finish"
    @keyup.esc="open = false"
  />

  <!-- список выносится в body: иначе он заперт в липкой шапке таблицы и уходит под карту -->
  <Teleport to="body">
    <ul v-if="open" class="time-dropdown" :style="dropdownStyle">
      <li
        v-for="time in suggestions"
        :key="time"
        :class="{ current: time === completeTime(text) }"
        @mousedown.prevent="choose(time)"
      >
        {{ time }}
      </li>
    </ul>
  </Teleport>
</template>

<style scoped>
.time-input {
  width: 68px;
  min-width: 0;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.time-dropdown {
  position: fixed;
  z-index: 1500; /* выше карты Leaflet (её слои и кнопки до 1000), ниже всплывающих уведомлений */
  max-height: 200px;
  margin: 0;
  padding: 4px 0;
  overflow-x: hidden;
  overflow-y: auto;
  list-style: none;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 6px 18px rgb(15 23 42 / 18%);
}

.time-dropdown li {
  padding: 4px 8px;
  text-align: center;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
}

.time-dropdown li:hover {
  background: #eff6ff;
}

.time-dropdown li.current {
  background: #2563eb;
  color: #fff;
}
</style>
