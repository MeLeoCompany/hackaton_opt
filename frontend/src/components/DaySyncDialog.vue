<script setup>
// Синхронизация дня с утверждённым планом на время: текущее (mode 'now') или заданное
// оператором (mode 'custom', время на выбранный день). Сначала — предпросмотр: какие заявки
// в какой статус перейдут и почему; «Новые» с прошедшим окном, которые уйдут в «Отменена», —
// отдельным предупреждением. Синхронизирует только кнопка «Синхронизировать».
import { computed, onMounted, ref, watch } from 'vue'

import { previewDaySync, runDaySync } from '../api/plansApi.js'
import { SYNC_GROUPS, formatSyncMoment } from '../utils/daySync.js'
import { formatDay, fromMoscowInputValue, moscowDateOf, moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { statusCode } from '../utils/requestStatuses.js'
import ErrorMessage from './ErrorMessage.vue'
import TimeInput from './TimeInput.vue'

const props = defineProps({
  planDate: { type: String, required: true },
  mode: { type: String, required: true }, // 'now' | 'custom'
  references: { type: Object, required: true },
  lastSyncedTo: { type: String, default: null }, // ISO: раньше этого времени синхронизировать нельзя
})
const emit = defineEmits(['close', 'done'])

// «сейчас» фиксируется при открытии окна: предпросмотр и синхронизация — на один момент
const openedAt = new Date().toISOString()
// заданное время — на выбранный день; по умолчанию текущее московское или прошлая синхронизация
const customTime = ref(
  props.lastSyncedTo && moscowDateOf(props.lastSyncedTo) === props.planDate
    ? moscowTimeOf(props.lastSyncedTo)
    : moscowTimeOf(openedAt),
)

const syncTime = computed(() => {
  if (props.mode === 'now') return openedAt
  return /^\d\d:\d\d$/.test(customTime.value) ? fromMoscowInputValue(`${props.planDate}T${customTime.value}`) : null
})

const report = ref(null)
const loading = ref(false)
const applying = ref(false)
const errorMessage = ref('')
const errorDetails = ref([])
let previewRequest = 0

async function loadPreview() {
  const request = ++previewRequest
  report.value = null
  errorMessage.value = ''
  errorDetails.value = []
  if (!syncTime.value) return
  loading.value = true
  try {
    const loaded = await previewDaySync(props.planDate, syncTime.value)
    if (request === previewRequest) report.value = loaded
  } catch (error) {
    if (request !== previewRequest) return
    errorMessage.value = error.message
    errorDetails.value = error.details ?? []
  } finally {
    if (request === previewRequest) loading.value = false
  }
}

async function apply() {
  applying.value = true
  errorMessage.value = ''
  try {
    emit('done', await runDaySync(props.planDate, syncTime.value))
  } catch (error) {
    errorMessage.value = error.message
    errorDetails.value = error.details ?? []
  } finally {
    applying.value = false
  }
}

const statusCodeOf = (statusId) => statusCode(props.references, statusId)

const groups = computed(() =>
  SYNC_GROUPS.map((group) => ({
    ...group,
    items: (report.value?.transitions ?? []).filter((item) => statusCodeOf(item.to_status_id) === group.code),
  })).filter((group) => group.items.length),
)

const warnings = computed(() => (report.value?.transitions ?? []).filter((item) => item.warning))

const canApply = computed(
  () => report.value && !report.value.problems.length && !loading.value && !applying.value,
)

onMounted(loadPreview)
watch(syncTime, loadPreview)
</script>

<template>
  <div class="dialog-backdrop" @click.self="$emit('close')">
    <div class="dialog" role="dialog" aria-label="Синхронизация дня с планом">
      <header>
        <strong>Синхронизация {{ formatDay(planDate) }} с планом</strong>
        <button class="close" title="Закрыть" @click="$emit('close')">×</button>
      </header>

      <div class="sync-time">
        <template v-if="mode === 'now'">
          На текущее время: <strong>{{ formatSyncMoment(openedAt, planDate) }}</strong>
        </template>
        <template v-else>
          <span>На время дня {{ formatDay(planDate) }}:</span>
          <TimeInput v-model="customTime" aria-label="время синхронизации" />
        </template>
        <span v-if="lastSyncedTo" class="muted">
          · прошлая синхронизация — на {{ formatSyncMoment(lastSyncedTo, planDate) }}, раньше нельзя
        </span>
      </div>

      <p class="muted sync-rule">
        По утверждённому плану: работы закончились — «Выполнена», бригада выехала — «В работе».
        Выполненные и отменённые заявки не меняются.
      </p>

      <ErrorMessage
        v-if="errorMessage"
        :message="errorMessage"
        :details="errorDetails"
        @close="errorMessage = ''"
      />
      <ErrorMessage
        v-if="report?.problems.length"
        message="Синхронизировать нельзя — ничего не изменится"
        :details="report.problems"
        @close="report.problems = []"
      />

      <p v-if="loading" class="muted">Считаю переходы…</p>

      <template v-else-if="report">
        <p v-if="report.approved_plan_id === null" class="muted">
          Утверждённого плана на этот день нет — отменяются только «Новые» заявки с прошедшим окном.
        </p>

        <div v-if="warnings.length" class="sync-warning" role="alert">
          ⚠ «Новых» заявок уйдёт в «Отменена»: {{ warnings.length }} — их окно уже закончилось, а в плане их
          нет. Если заявку ещё можно выполнить, поправьте её окно или постройте план заново.
        </div>

        <p v-if="!report.transitions.length" class="muted">
          Менять нечего: на это время статусы уже соответствуют плану.
        </p>

        <section v-for="group in groups" :key="group.code" class="sync-group">
          <h4>
            <span :class="['status-badge', 'status-fixed', `status-${group.code}`]">
              {{ referenceName(references, 'request_statuses', group.items[0].to_status_id) }}
            </span>
            {{ group.title }} · {{ group.items.length }}
          </h4>
          <ul>
            <li v-for="item in group.items" :key="item.request_id" :class="{ warning: item.warning }">
              <span class="sync-request">№{{ item.request_id }}</span>
              <span class="sync-address">{{ item.address }}</span>
              <span class="sync-reason muted">{{ item.reason }}</span>
            </li>
          </ul>
        </section>
      </template>

      <footer>
        <button @click="$emit('close')">Отмена</button>
        <button class="primary" :disabled="!canApply" @click="apply">
          {{ applying ? 'Синхронизирую…' : 'Синхронизировать' }}
        </button>
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
  width: min(760px, 94vw);
  max-height: 86vh;
  padding: 14px;
  overflow: auto;
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

.sync-time {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.sync-time :deep(input) {
  width: 72px;
}

.sync-rule {
  font-size: 12px;
}

.sync-warning {
  padding: 8px 12px;
  border-radius: 8px;
  background: #fffbeb;
  color: #92400e;
}

.sync-group h4 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0 6px;
  font-size: 13px;
  font-weight: 600;
}

.sync-group ul {
  margin: 0;
  padding: 0;
  list-style: none;
}

/* номер | адрес | почему — колонки одной ширины во всех строках */
.sync-group li {
  display: grid;
  grid-template-columns: 90px minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 12px;
  padding: 5px 8px;
  border-top: 1px solid #e2e8f0;
}

.sync-group li.warning {
  background: #fffbeb;
}

.sync-request {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.sync-address,
.sync-reason {
  overflow-wrap: anywhere;
}

footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 10px;
  border-top: 1px solid #e2e8f0;
}
</style>
