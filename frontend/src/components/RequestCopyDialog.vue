<script setup>
// Копия отменённой заявки: та же работа заново. День можно оставить прежний или выбрать другой —
// например, когда работу перенесли на завтра.
import { ref } from 'vue'

import { formatDay, moscowDateOf } from '../utils/moscowTime.js'

const props = defineProps({
  request: { type: Object, required: true },
})
const emit = defineEmits(['copy', 'close'])

const sourceDay = moscowDateOf(props.request.window_start)
const day = ref(sourceDay)
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog" role="dialog" :aria-label="`Копия заявки №${request.id}`">
      <header>
        <strong>Копия отменённой заявки №{{ request.id }}</strong>
        <button class="close" title="Закрыть" @click="emit('close')">×</button>
      </header>

      <p class="muted">
        {{ request.address }} · окно останется тем же по времени суток. Копия будет «Новой» — её
        можно поправить и спланировать.
      </p>

      <label class="field">
        <span>День копии</span>
        <input v-model="day" type="date" />
      </label>
      <p v-if="day !== sourceDay" class="muted">
        Заявка переедет с {{ formatDay(sourceDay) }} на {{ formatDay(day) }}.
      </p>

      <footer>
        <span class="muted">Исходная заявка останется отменённой</span>
        <span class="buttons">
          <button class="primary" :disabled="!day" @click="emit('copy', day)">Создать копию</button>
          <button @click="emit('close')">Отмена</button>
        </span>
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
  gap: 10px;
  width: min(460px, 92vw);
  padding: 14px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(15 23 42 / 30%);
}

.dialog header,
.dialog footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.field {
  display: flex;
  align-items: center;
  gap: 10px;
}

.field span {
  width: 100px;
  color: #475569;
  font-size: 13px;
}

.buttons {
  display: flex;
  gap: 8px;
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
