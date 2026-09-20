<script setup>
// Копия отменённой заявки: та же работа заново. Слева — день исходной заявки, справа — день
// копии: по умолчанию тот же, но работу можно перенести на другой.
import { computed, ref } from 'vue'

import { formatDay, moscowDateOf, moscowTimeOf } from '../utils/moscowTime.js'

const props = defineProps({
  request: { type: Object, required: true },
})
const emit = defineEmits(['copy', 'close'])

const sourceDay = moscowDateOf(props.request.window_start)
const day = ref(sourceDay)
const moved = computed(() => day.value && day.value !== sourceDay)
// только время: день показан выше, в переносе
const window = computed(() => `${moscowTimeOf(props.request.window_start)}–${moscowTimeOf(props.request.window_end)}`)
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog" role="dialog" :aria-label="`Копия заявки №${request.id}`">
      <header>
        <strong>Копия заявки №{{ request.id }}</strong>
        <button class="close" title="Закрыть" @click="emit('close')">×</button>
      </header>

      <p class="address">{{ request.address }}</p>

      <div class="move">
        <div class="from">
          <span class="caption">Отменена</span>
          <strong>{{ formatDay(sourceDay) }}</strong>
        </div>
        <span class="arrow" aria-hidden="true">→</span>
        <label class="to">
          <span class="caption">Копия на день</span>
          <input v-model="day" type="date" aria-label="день копии" />
        </label>
      </div>

      <p class="window">Окно {{ window }}{{ moved ? ' — то же время в новом дне' : '' }}</p>

      <footer>
        <button class="primary" :disabled="!day" @click="emit('copy', day)">
          {{ moved ? 'Создать копию с переносом' : 'Создать копию' }}
        </button>
        <button @click="emit('close')">Отмена</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgb(15 23 42 / 45%);
}

.dialog {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: min(440px, 92vw);
  padding: 16px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(15 23 42 / 30%);
}

.dialog header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.dialog footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.address {
  margin: 0;
  color: #334155;
  font-size: 14px;
}

/* перенос: слева день отменённой заявки, стрелка, справа день копии */
.move {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}

.from,
.to {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.from strong {
  padding: 5px 0;
  color: #64748b;
  font-size: 14px;
  font-weight: 600;
}

.caption {
  color: #94a3b8;
  font-size: 12px;
}

.arrow {
  padding-bottom: 6px;
  color: #94a3b8;
  font-size: 18px;
}

.to input {
  width: 100%;
  box-sizing: border-box;
}

.window {
  margin: 0;
  color: #64748b;
  font-size: 13px;
}

.close {
  border: none;
  background: none;
  color: #64748b;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}
</style>
