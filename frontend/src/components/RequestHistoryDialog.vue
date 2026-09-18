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

// кто сменил: оператор по имени; системный переход — «система», а если его запустил
// человек (утвердил план) — «система · имя»
function whoChanged(entry) {
  if (entry.manual) return entry.user_name ?? 'оператор'
  return entry.user_name ? `система · ${entry.user_name}` : 'система'
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
        <li v-for="entry in entries" :key="entry.id">
          <span class="history-when">
            {{ formatDay(moscowDateOf(entry.changed_at)) }}
            <strong>{{ moscowTimeOf(entry.changed_at) }}</strong>
          </span>
          <span class="history-change">
            <template v-if="entry.from_status_id !== null">
              <span :class="['status-badge', `status-${statusCode(references, entry.from_status_id)}`]">
                {{ referenceName(references, 'request_statuses', entry.from_status_id) }}
              </span>
              <span class="history-arrow" aria-hidden="true">→</span>
            </template>
            <span :class="['status-badge', `status-${statusCode(references, entry.to_status_id)}`]">
              {{ referenceName(references, 'request_statuses', entry.to_status_id) }}
            </span>
          </span>
          <span class="history-details muted">
            {{ whoChanged(entry) }}<template v-if="entry.plan_id !== null"> · план №{{ entry.plan_id }}</template
            ><template v-if="entry.comment"> · {{ entry.comment }}</template>
          </span>
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
  width: min(620px, 92vw);
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

/* записи по порядку сверху вниз: когда · что сменилось · кто и почему */
.history {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  overflow: auto;
  list-style: none;
}

.history li {
  display: grid;
  grid-template-columns: 130px auto 1fr;
  align-items: center;
  gap: 12px;
  padding: 7px 0;
  border-top: 1px solid #e2e8f0;
}

.history li:first-child {
  border-top: 0;
}

.history-when {
  color: #475569;
  font-variant-numeric: tabular-nums;
}

.history-change {
  display: flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.history-arrow {
  color: #94a3b8;
}

.history-details {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
