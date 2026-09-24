<script setup>
// Что делать с заявками, которые не вошли в план (docs/algoV2.md, шаги 2-5).
// Два режима, и разница между ними принципиальная:
//   approve — «Утвердить»: расчёта нет вовсе. Оператор переносит невлезшие на другой день
//     или отменяет, работы в дне становится меньше, маршруты не меняются — утверждается
//     ровно тот план, который на экране;
//   windows — «Подобрать окна»: второй расчёт с раскрытыми окнами говорит, когда бригада
//     сможет приехать; клиент соглашается — день считается заново новым черновиком.
// Невлезшую заявку «Новой» без решения не оставляем: сервер без решений черновик не утвердит.
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
  // approve — утверждаем без расчёта, windows — подбираем окна вторым расчётом
  mode: { type: String, default: 'approve' },
})

const windowsMode = computed(() => props.mode === 'windows')
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
  // расчёт идёт только при подборе окон: при утверждении мы просто спрашиваем список
  if (windowsMode.value) watchRun(runId)
  try {
    const result = await previewApproval(props.summary.id, {
      run_id: runId,
      suggest: windowsMode.value,
    })
    setPreview(result, { allowAgree: windowsMode.value })
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

// список невлезших нужен сразу в обоих режимах: без решений по ним утвердить нельзя
onMounted(searchWindows)

onBeforeUnmount(() => {
  if (searching.value) cancelRun()
})
</script>

<template>
  <div class="dialog-backdrop" @click.self="close">
    <div class="dialog" :class="{ wide: problems.length }" role="dialog" aria-label="Утверждение плана">
      <header>
        <strong>
          {{ windowsMode ? 'Подбор окон' : 'Утверждение плана' }} №{{ summary.id }} ·
          {{ formatDay(summary.plan_date) }}
        </strong>
        <button class="close" title="Закрыть" @click="close">×</button>
      </header>

      <p v-if="windowsMode" class="hint">
        Не вошло в план: {{ summary.unassigned_count }}. Второй расчёт с раскрытыми окнами
        говорит, когда бригада сможет приехать. Клиент согласился — день посчитается заново
        отдельным расчётом; уже размещённые заявки из него не выпадут.
      </p>
      <p v-else class="hint">
        Не вошло в план: {{ summary.unassigned_count }}. Перенесите их на другой день или
        отмените — расчёт утвердится как есть, без пересчёта. Если хотите попробовать вместить
        их сегодня, закройте окно и нажмите «Подобрать окна».
      </p>

      <PlanRunProgress v-if="searching" :run="run" @cancel="cancelRun" />
      <p v-if="searchError" class="error">{{ searchError }}</p>

      <p v-if="preview && !problems.length" class="hint">
        Звонить некому: невлезшие заявки уже не ждут планирования — закреплены за другим планом,
        сняты или решены. План можно утверждать.
      </p>

      <UnassignedDecisions
        v-if="problems.length"
        :title="
          windowsMode
            ? `Не влезли: ${problems.length} — обзвоните клиентов`
            : `Не влезли: ${problems.length} — решите по каждой`
        "
        :problems="problems"
        :decisions="decisions"
        :tolerance="tolerance"
        :disabled="building"
        :with-agree="windowsMode"
      >
        <template v-if="windowsMode">
          Время подобрано с раскрытыми окнами, вошедшие в план заявки не сдвигаются. Решение нужно
          по каждой; перенесённая войдёт в план своего дня.</template
        ><template v-else>
          Сегодня они не влезли. Перенос и отмена только убирают работу из дня, маршруты бригад
          от этого не меняются.</template
        ><template v-if="skipped">
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
          {{
            building
              ? 'Считаю…'
              : windowsMode
                ? 'Учесть решения и пересчитать'
                : 'Применить решения и утвердить'
          }}
        </button>
        <!-- решать не по кому — утверждаем; подбор прервали или он упал — можно повторить -->
        <button v-else-if="preview" class="primary" :disabled="building" @click="emit('approve')">
          Утвердить
        </button>
        <button v-else class="primary" :disabled="building || searching" @click="searchWindows">
          {{ searching ? 'Читаю…' : 'Повторить' }}
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
