<script setup>
// «Не выполнить»: бригада выбирает причину — она уходит в историю заявки, заявка отменяется.
import { computed, ref } from 'vue'

const props = defineProps({
  visit: { type: Object, required: true },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['confirm', 'close'])

const REASONS = ['Клиента нет на месте', 'Нет доступа в помещение', 'Нет нужного оборудования', 'Клиент отказался']
const choice = ref('')
const other = ref('')
const reason = computed(() => (choice.value === 'other' ? other.value.trim() : choice.value))
</script>

<template>
  <div class="sheet-backdrop" @click.self="emit('close')">
    <section class="sheet" role="dialog" aria-label="Почему не выполнить заявку">
      <h2>Не выполнить заявку №{{ props.visit.request_id }}?</h2>
      <p class="hint">Заявка будет отменена. Выберите причину — диспетчер её увидит.</p>
      <label v-for="item in REASONS" :key="item" class="option">
        <input v-model="choice" type="radio" :value="item" />
        <span>{{ item }}</span>
      </label>
      <label class="option">
        <input v-model="choice" type="radio" value="other" />
        <span>Другое</span>
      </label>
      <textarea v-if="choice === 'other'" v-model="other" rows="2" placeholder="Что случилось" />
      <div class="actions">
        <button class="danger big" :disabled="!reason || busy" @click="emit('confirm', reason)">
          Не выполнить
        </button>
        <button class="ghost" @click="emit('close')">Назад</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.sheet-backdrop {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: flex;
  align-items: flex-end;
  background: rgb(17 24 39 / 45%);
}

.sheet {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  padding: 18px 18px 24px;
  border-radius: 18px 18px 0 0;
  background: #fff;
}

h2 {
  margin: 0;
  font-size: 18px;
}

.hint {
  margin: 0;
  color: #6b7280;
  font-size: 14px;
}

.option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  font-size: 15px;
}

.option input {
  width: 18px;
  height: 18px;
}

textarea {
  padding: 10px 12px;
  border: 1px solid #d1d5db;
  border-radius: 12px;
  font: inherit;
}

.actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 6px;
}
</style>
