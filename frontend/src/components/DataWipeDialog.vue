<script setup>
// Очистка перед показом: удаляет всё наработанное, оставляя справочники и учётки.
// Отменить нельзя, поэтому подтверждение — слово руками, а не просто вторая кнопка.
import { computed, onMounted, ref } from 'vue'

// props именно переменной: в шаблоне имя видно и так, а в обработчике submit() без неё
// получался ReferenceError — кнопка просто переставала работать
const props = defineProps({
  // сколько чего сейчас в базе: «Заявки: 409» — чтобы видеть, что именно уйдёт
  counts: { type: Object, default: () => ({}) },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['wipe', 'close'])

const WIPE_WORD = 'УДАЛИТЬ'
const word = ref('')
const input = ref(null)
const ready = computed(() => word.value.trim().toUpperCase() === WIPE_WORD)

// удаляемое и остающееся: список короче и честнее, чем абзац текста
const REMOVED = 'заявки и факты по ним, планы с маршрутами и назначениями, журнал расчётов, отметки бригад, смены инженеров'
const KEPT = 'офисы, бригады, оборудование, нормы, приоритеты, учётные записи'

onMounted(() => input.value?.focus())

function submit() {
  if (ready.value && !props.busy) emit('wipe', word.value)
}
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog" role="dialog" aria-label="Очистка данных перед показом">
      <header>
        <strong>Очистить все данные?</strong>
        <button class="close" title="Закрыть" @click="emit('close')">×</button>
      </header>

      <dl class="scope">
        <div class="removed">
          <dt>Удалю</dt>
          <dd>{{ REMOVED }}</dd>
        </div>
        <div>
          <dt>Оставлю</dt>
          <dd>{{ KEPT }}</dd>
        </div>
      </dl>

      <p v-if="Object.keys(counts).length" class="muted">
        Сейчас в базе: <template v-for="(count, name, index) in counts" :key="name"
          ><span v-if="index">, </span>{{ name.toLowerCase() }} {{ count }}</template>.
      </p>

      <p class="warn">Отменить нельзя: вернуть данные можно только загрузкой заново.</p>

      <label class="confirm">
        <span>Введите <strong>{{ WIPE_WORD }}</strong>, чтобы подтвердить</span>
        <input
          ref="input"
          v-model="word"
          :disabled="busy"
          autocomplete="off"
          :placeholder="WIPE_WORD"
          @keyup.enter="submit"
        />
      </label>

      <footer>
        <span></span>
        <span class="buttons">
          <button class="danger" :disabled="busy || !ready" @click="submit">
            {{ busy ? 'Удаляю…' : 'Удалить безвозвратно' }}
          </button>
          <button :disabled="busy" @click="emit('close')">Отмена</button>
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

.scope {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
}

.scope div {
  display: flex;
  gap: 8px;
}

.scope dt {
  flex: none;
  width: 68px;
  color: #475569;
}

.scope dd {
  margin: 0;
}

.scope .removed dd {
  color: #b91c1c;
}

.warn {
  margin: 0;
  color: #b91c1c;
  font-size: 13px;
}

.confirm {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 13px;
}

.confirm input {
  flex: 1;
  min-width: 0;
  padding: 6px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
}

.danger {
  border: 1px solid #b91c1c;
  background: #b91c1c;
  color: #fff;
}

.danger:disabled {
  border-color: #e3b1b1;
  background: #e3b1b1;
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
