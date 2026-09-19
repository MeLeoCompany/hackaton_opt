<script setup>
// История статуса заявки: когда, из какого в какой, кто и по какому плану.
// Нужна, чтобы при пересчётах понимать, что с заявкой происходило.
import { onMounted, ref } from 'vue'

import { getRequestHistory } from '../api/requestsApi.js'
import { formatDay, moscowDateOf, moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { statusCode } from '../utils/requestStatuses.js'

const props = defineProps({
  requestId: { type: Number, required: true },
  references: { type: Object, required: true },
})
defineEmits(['close'])

const entries = ref([])
const loading = ref(true)
const errorMessage = ref('')

onMounted(async () => {
  try {
    entries.value = await getRequestHistory(props.requestId)
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
})

// кто сменил: по имени; без имени — «система» (сама, например при переносе данных)
function whoChanged(entry) {
  return entry.user_name ?? (entry.manual ? 'Оператор' : 'Система')
}
</script>

<template>
  <div class="dialog-backdrop" @click.self="$emit('close')" @keydown.esc="$emit('close')">
    <div class="dialog" role="dialog" :aria-label="`История заявки №${requestId}`">
      <header>
        <strong>История заявки №{{ requestId }}</strong>
        <button class="close" title="Закрыть" @click="$emit('close')">×</button>
      </header>

      <p v-if="loading" class="muted">Загружаю историю…</p>
      <p v-else-if="errorMessage" class="message error">{{ errorMessage }}</p>
      <p v-else-if="!entries.length" class="muted">Статус заявки ещё не менялся</p>

      <ol v-else class="history">
        <!-- шапка колонок: без неё «Администратор» и «№22» в строках читаются хуже -->
        <li class="history-head" aria-hidden="true">
          <span>Когда</span>
          <span>Переход</span>
          <span>Пользователь</span>
          <span>План</span>
        </li>
        <li v-for="entry in entries" :key="entry.id" :title="entry.comment">
          <span class="history-when">
            {{ formatDay(moscowDateOf(entry.changed_at)) }}
            <strong>{{ moscowTimeOf(entry.changed_at) }}</strong>
          </span>
          <!-- переход — своя колонка с плашками одной ширины: «из» и «в» стоят ровно друг под
               другом во всех строках; у появления заявки «из» пусто, место остаётся -->
          <span class="history-change">
            <span
              v-if="entry.from_status_id !== null"
              :class="['status-badge', 'status-fixed', `status-${statusCode(references, entry.from_status_id)}`]"
            >
              {{ referenceName(references, 'request_statuses', entry.from_status_id) }}
            </span>
            <span v-else class="history-appeared">появилась</span>
            <span class="history-arrow" aria-hidden="true">→</span>
            <span :class="['status-badge', 'status-fixed', `status-${statusCode(references, entry.to_status_id)}`]">
              {{ referenceName(references, 'request_statuses', entry.to_status_id) }}
            </span>
          </span>
          <!-- кто и по какому плану — каждое своей колонкой; пояснение перехода — подсказкой
               на строке, чтобы не загромождать -->
          <span class="history-who">{{ whoChanged(entry) }}</span>
          <span class="history-plan">{{ entry.plan_id !== null ? `№${entry.plan_id}` : '—' }}</span>
        </li>
      </ol>
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
  width: min(760px, 94vw);
  max-height: 80vh;
  padding: 14px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(15 23 42 / 30%);
  font-size: 13px;
}

.dialog header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.close {
  padding: 0 8px;
  font-size: 18px;
  line-height: 26px;
}

.dialog p {
  margin: 0;
}

/* записи по порядку сверху вниз: когда · что сменилось · кто · по какому плану */
.history {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  overflow: auto;
  list-style: none;
}

/* четыре колонки одной ширины во всех строках: когда | переход | кто | план;
   между ними вертикальные черты */
.history li {
  display: grid;
  grid-template-columns: 124px 252px minmax(0, 1fr) 72px;
  align-items: center;
  padding: 7px 0;
  border-top: 1px solid #e2e8f0;
}

.history li > * {
  padding: 0 12px;
}

.history li > *:first-child {
  padding-left: 0;
}

.history li > * + * {
  align-self: stretch;
  display: flex;
  align-items: center;
  border-left: 1px solid #e2e8f0;
}

.history li:first-child {
  border-top: 0;
}

.history-when {
  color: #475569;
  font-variant-numeric: tabular-nums;
}

.history-change {
  gap: 6px;
  white-space: nowrap;
}

.history-appeared {
  box-sizing: border-box;
  width: 100px;
  color: #94a3b8;
  font-size: 12px;
  text-align: center;
}

.history-arrow {
  color: #94a3b8;
}

.history-head {
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.history-who {
  min-width: 0;
  overflow-wrap: anywhere;
}

.history-plan {
  color: #475569;
  font-variant-numeric: tabular-nums;
}

</style>
