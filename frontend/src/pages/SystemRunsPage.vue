<script setup>
// Журнал расчётов: какие планы считались, сколько это заняло и на чём расчёт стоял.
// Строка раскрывается в подробный ход — шаг за шагом, с процентами и временем.
import { computed, onMounted, ref } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import { fetchPlanRun, listPlanRuns } from '../api/systemApi.js'
import { usePlanFocus } from '../composables/usePlanFocus.js'
import { formatDay, moscowTimeOf } from '../utils/moscowTime.js'

const KIND_NAMES = { build: 'расчёт дня', replan: 'пересчёт', preview: 'пробный пересчёт' }
const STATUS_NAMES = { running: 'идёт', done: 'готов', failed: 'ошибка' }

const runs = ref([])
const loading = ref(false)
const errorMessage = ref('')
const openedId = ref(null)
const opened = ref(null)

const { openPlan } = usePlanFocus()

async function load() {
  loading.value = true
  errorMessage.value = ''
  try {
    runs.value = await listPlanRuns(100)
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

// раскрыли строку — читаем её шаги; повторный клик закрывает
async function toggle(run) {
  if (openedId.value === run.id) {
    openedId.value = null
    opened.value = null
    return
  }
  openedId.value = run.id
  opened.value = null
  try {
    opened.value = await fetchPlanRun(run.id)
  } catch (error) {
    errorMessage.value = error.message
  }
}

const running = computed(() => runs.value.filter((run) => run.status === 'running').length)

function duration(run) {
  const seconds = run.duration_seconds ?? 0
  return seconds < 60 ? `${seconds.toFixed(1)} с` : `${Math.floor(seconds / 60)} мин ${Math.round(seconds % 60)} с`
}

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Журнал расчётов</h1>
      <p>
        Записей {{ runs.length }}<template v-if="running"> · сейчас считается {{ running }}</template> ·
        время московское
      </p>
    </header>

    <ErrorMessage v-if="errorMessage" :message="errorMessage" @close="errorMessage = ''" />

    <div class="list-bar">
      <button :disabled="loading" @click="load">{{ loading ? 'Обновляю…' : 'Обновить' }}</button>
    </div>

    <div class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th>Начат</th>
            <th>Что считали</th>
            <th>День</th>
            <th>Решатель</th>
            <th>Состояние</th>
            <th>Длительность</th>
            <th>План</th>
            <th>Кто запустил</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!runs.length && !loading">
            <td colspan="8" class="empty">Расчётов ещё не было</td>
          </tr>
          <template v-for="run in runs" :key="run.id">
            <tr :class="{ selected: run.id === openedId }" @click="toggle(run)">
              <td class="nowrap">{{ moscowTimeOf(run.started_at) }}</td>
              <td class="nowrap">{{ KIND_NAMES[run.kind] ?? run.kind }}</td>
              <td class="nowrap">{{ run.plan_date ? formatDay(run.plan_date) : '—' }}</td>
              <td>{{ run.solver ?? '—' }}</td>
              <td>
                <span :class="['badge', `run-${run.status}`]">{{ STATUS_NAMES[run.status] ?? run.status }}</span>
                <span v-if="run.status === 'running'" class="muted"> · {{ run.step }} ({{ run.progress }}%)</span>
                <span v-else-if="run.error" class="run-error">{{ run.error }}</span>
              </td>
              <td class="nowrap">{{ duration(run) }}</td>
              <td class="nowrap">
                <button v-if="run.plan_id" class="link" @click.stop="openPlan(run.plan_id)">№{{ run.plan_id }}</button>
                <span v-else class="muted">—</span>
              </td>
              <td>{{ run.user_name ?? '—' }}</td>
            </tr>
            <!-- ход расчёта по шагам: видно, где он стоял дольше всего -->
            <tr v-if="run.id === openedId" class="steps-row">
              <td colspan="8">
                <p v-if="!opened" class="muted">Читаю ход расчёта…</p>
                <ol v-else class="steps">
                  <li v-for="(event, index) in opened.events" :key="index" :class="event.level">
                    <span class="at">{{ moscowTimeOf(event.at) }}</span>
                    <span class="percent">{{ event.progress ?? '' }}<template v-if="event.progress !== null">%</template></span>
                    <span :class="{ title: event.message === event.step }">{{ event.message }}</span>
                  </li>
                </ol>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.badge.run-running {
  background: #dbeafe;
  color: #1d4ed8;
}

.badge.run-done {
  background: #dcfce7;
  color: #166534;
}

.badge.run-failed {
  background: #fee2e2;
  color: #b91c1c;
}

.run-error {
  margin-left: 6px;
  color: #b91c1c;
  font-size: 12px;
}

.steps-row td {
  background: #f8fafc;
}

.steps {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 4px 0;
  list-style: none;
  font-size: 12px;
}

.steps li {
  display: flex;
  gap: 10px;
}

.steps li.warning {
  color: #b45309;
}

.steps li.error {
  color: #b91c1c;
}

.steps .at,
.steps .percent {
  flex: none;
  width: 56px;
  color: #94a3b8;
  font-variant-numeric: tabular-nums;
}

.steps .percent {
  width: 40px;
  text-align: right;
}

.steps .title {
  font-weight: 600;
}
</style>
