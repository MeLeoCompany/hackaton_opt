<script setup>
// Утверждение черновика, в который вошли не все заявки (docs/algoV2.md, шаги 2-5).
// Невлезшую заявку «Новой» без решения не оставляем: второй расчёт с раскрытыми окнами
// говорит, когда бригада сможет приехать, оператор обзванивает клиентов и по каждой решает —
// согласованное время, перенос на другой день или отмена. По решениям день считается заново —
// новым черновиком, который утверждают отдельно. Сервер без решений черновик не утвердит.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { previewApproval } from '../api/plansApi.js'
import { usePlanRun } from '../composables/usePlanRun.js'
import { useUnassignedDecisions } from '../composables/useUnassignedDecisions.js'
import { formatDay } from '../utils/moscowTime.js'
import PlanRunProgress from './PlanRunProgress.vue'
import UnassignedDecisions from './UnassignedDecisions.vue'

const props = defineProps({
  summary: { type: Object, required: true }, // сводка утверждаемого черновика
  building: { type: Boolean, required: true },
})
const emit = defineEmits(['approve', 'decide', 'close'])

const { preview, decisions, problems, tolerance, setPreview, decisionsReady, payload } =
  useUnassignedDecisions(() => props.summary.plan_date)

// невлезшие, по которым звонить не нужно: их уже забрал другой план или сняли
const skipped = computed(() => Math.max(0, props.summary.unassigned_count - problems.value.length))

// второй расчёт идёт минутами на большом дне — показываем его ход и даём прервать
const { run, newRunId, watch: watchRun, cancel: cancelRun, stop: stopRun } = usePlanRun()
const searching = ref(false)
const searchError = ref('')

async function searchWindows() {
  searching.value = true
  searchError.value = ''
  const runId = newRunId()
  watchRun(runId)
  try {
    setPreview(await previewApproval(props.summary.id, { run_id: runId }))
  } catch (error) {
    searchError.value = [error.message, ...(error.details ?? [])].join(': ')
  } finally {
    stopRun()
    searching.value = false
  }
}

// закрыли окно посреди подбора — расчёт на сервере больше не нужен
async function close() {
  if (searching.value) await cancelRun()
  emit('close')
}

// окна подбираем сразу: без решений по невлезшим утвердить всё равно нельзя
onMounted(searchWindows)

onBeforeUnmount(() => {
  if (searching.value) cancelRun()
})
</script>

<template>
  <div class="dialog-backdrop" @click.self="close">
    <div class="dialog" :class="{ wide: problems.length }" role="dialog" aria-label="Утверждение плана">
      <header>
        <strong>Утверждение плана №{{ summary.id }} · {{ formatDay(summary.plan_date) }}</strong>
        <button class="close" title="Закрыть" @click="close">×</button>
      </header>

      <p class="hint">
        Не вошло в план: {{ summary.unassigned_count }}. Без решения их не оставляем: второй расчёт
        предложит клиентам время, а по их ответам день пересчитается новым черновиком.
      </p>

      <PlanRunProgress v-if="searching" :run="run" @cancel="cancelRun" />
      <p v-if="searchError" class="error">{{ searchError }}</p>

      <p v-if="preview && !problems.length" class="hint">
        Звонить некому: невлезшие заявки уже не ждут планирования — закреплены за другим планом,
        сняты или решены. План можно утверждать.
      </p>

      <UnassignedDecisions
        v-if="problems.length"
        :title="`Не влезли: ${problems.length} — обзвоните клиентов`"
        :problems="problems"
        :decisions="decisions"
        :tolerance="tolerance"
        :disabled="building"
      >
        Время подобрано с раскрытыми окнами, вошедшие в план заявки не сдвигаются. Решение нужно по
        каждой; перенесённая войдёт в план своего дня.<template v-if="skipped">
          Ещё {{ skipped }} уже не ждут планирования: закреплены за другим планом или сняты.</template
        >
      </UnassignedDecisions>

      <footer>
        <button
          v-if="problems.length"
          class="primary"
          :disabled="building || !decisionsReady"
          @click="emit('decide', { decisions: payload() })"
        >
          {{ building ? 'Считаю…' : 'Учесть решения и пересчитать' }}
        </button>
        <!-- решать не по кому — утверждаем; подбор прервали или он упал — можно повторить -->
        <button v-else-if="preview" class="primary" :disabled="building" @click="emit('approve')">
          Утвердить
        </button>
        <button v-else class="primary" :disabled="building || searching" @click="searchWindows">
          {{ searching ? 'Подбираю…' : 'Подобрать окна' }}
        </button>
        <button class="cancel" :disabled="building" @click="close">Отмена</button>
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
  width: min(520px, 92vw);
  padding: 14px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(15 23 42 / 30%);
}

.dialog.wide {
  width: min(760px, 94vw);
  max-height: 90vh;
  overflow: auto;
}

.dialog header,
.dialog footer {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dialog header {
  justify-content: space-between;
}

.dialog footer .cancel {
  margin-left: auto;
}

.close {
  padding: 0 8px;
  font-size: 18px;
  line-height: 26px;
}

.hint {
  margin: 0;
  color: #64748b;
  font-size: 12px;
}

.error {
  margin: 0;
  color: #b91c1c;
  font-size: 13px;
}
</style>
