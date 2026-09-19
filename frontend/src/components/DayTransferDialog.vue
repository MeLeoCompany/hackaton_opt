<script setup>
// Перенос слепка дня из CSV в выбранный день. Отдельно спрашиваем про отменённые заявки:
// их отменили в том дне, а не в этом, поэтому переносить их отменёнными странно.
import { ref } from 'vue'

import { formatDay } from '../utils/moscowTime.js'

defineProps({
  fileName: { type: String, required: true },
  day: { type: String, required: true },
  // сколько заявок уже есть в этом дне: файл их не заменит, а добавится к ним
  existing: { type: Number, default: 0 },
})
const emit = defineEmits(['transfer', 'close'])

const cancelled = ref('skip')
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog" role="dialog" aria-label="Перенос заявок в день">
      <header>
        <strong>Перенести заявки в {{ formatDay(day) }}</strong>
        <button class="close" title="Закрыть" @click="emit('close')">×</button>
      </header>

      <p class="muted">
        Файл «{{ fileName }}» ляжет в этот день копией: время суток то же, номера новые.
        <template v-if="existing">
          В дне уже есть заявок: {{ existing }} — они останутся, файл добавится к ним.
        </template>
      </p>

      <fieldset>
        <legend>Отменённые заявки из файла</legend>
        <label><input v-model="cancelled" type="radio" value="skip" /> не переносить</label>
        <label><input v-model="cancelled" type="radio" value="as_new" /> перенести «Новыми»</label>
        <p class="muted">В новом дне эту работу ещё никто не отменял — решайте, нужна ли она.</p>
      </fieldset>

      <footer>
        <span></span>
        <span class="buttons">
          <button class="primary" @click="emit('transfer', cancelled)">Перенести</button>
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
  width: min(480px, 92vw);
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

fieldset {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
}

legend {
  padding: 0 4px;
  color: #475569;
  font-size: 13px;
}

fieldset label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}

fieldset .muted {
  margin: 2px 0 0;
  font-size: 12px;
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
