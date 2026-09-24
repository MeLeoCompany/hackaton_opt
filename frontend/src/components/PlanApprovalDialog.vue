<script setup>
// Что делать с заявками, которые не вошли в план (docs/algoV2.md, шаги 2-5).
// Два режима:
//   approve — «Утвердить»: оператор переносит невлезшие на другой день или отменяет,
//     работы в дне становится меньше, маршруты не меняются;
//   windows — «Подобрать окна»: идёт второй расчёт с раскрытыми окнами, и получается новый
//     расчёт дня. Решения принимаются сразу по нему: клиент согласился — заявка остаётся
//     ровно там, куда её поставил расчёт, отказался — её вычёркивают.
// Ни в том, ни в другом случае день заново не считается: выпадать некому.
// Невлезшую заявку «Новой» без решения не оставляем: сервер без решений расчёт не утвердит.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { dropWindows, pickWindows, previewApproval } from '../api/plansApi.js'
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

// подбор окон даёт новый расчёт дня: решения дальше принимаются уже по нему
const decidedPlanId = ref(props.summary.id)

// после подбора окон счёт идёт по новому расчёту: в исходном невлезших было больше, часть
// из них подбор разместил, и решать по ним уже нечего
const waiting = computed(() =>
  preview.value ? problems.value.length : props.summary.unassigned_count,
)

// невлезшие, по которым звонить не нужно: их уже забрал другой план или сняли
const skipped = computed(() =>
  windowsMode.value || !preview.value
    ? 0
    : Math.max(0, props.summary.unassigned_count - problems.value.length),
)

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
    const result = windowsMode.value
      ? await pickWindows(props.summary.id, { run_id: runId })
      : await previewApproval(props.summary.id, { run_id: runId })
    decidedPlanId.value = result.plan_id ?? props.summary.id
    setPreview(result, { allowAgree: windowsMode.value })
  } catch (error) {
    searchError.value = [error.message, ...(error.details ?? [])].join(': ')
  } finally {
    stopRun()
    searching.value = false
  }
}

// подбор окон уже дал новый расчёт дня; пока решения не применены, его можно выбросить
const picked = computed(() => windowsMode.value && decidedPlanId.value !== props.summary.id)
const dropping = ref(false)

// Отмена подбора: предложенные времена не годятся — расчёт выбрасываем и возвращаемся
// к исходному плану. Его утверждают как обычно: перенести, отменить или «не дозвонились».
// Крестик и клик мимо окна делают то же самое: подбор — дело добровольное
async function close() {
  if (searching.value) await cancelRun()
  if (!picked.value) {
    emit('close', {})
    return
  }
  dropping.value = true
  try {
    await dropWindows(decidedPlanId.value)
  } catch {
    // решения уже применены — расчёт остаётся, его видно в списке планов
  } finally {
    dropping.value = false
    emit('close', { planned: true })
  }
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
        Второй расчёт с раскрытыми окнами разложил день заново и говорит, когда бригада сможет
        приехать. Решения ждут: {{ waiting }}. «Принять» — решения применятся, и этот расчёт
        останется утвердить одной кнопкой. «Отмена» — вернёмся к прежнему расчёту, его тоже
        можно утвердить: перенести эти заявки, отменить или отметить «не дозвонились».
      </p>
      <p v-else class="hint">
        Не вошло в план: {{ waiting }}. Перенесите их на другой день или отмените — расчёт
        утвердится как есть, без пересчёта. Если хотите попробовать вместить их сегодня,
        закройте окно и нажмите «Подобрать окна».
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
          Время подобрано этим же расчётом: по нему бригада и приедет. Решение нужно по каждой;
          перенесённая войдёт в план своего дня.</template
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
          @click="emit('decide', { planId: decidedPlanId, decisions: payload() })"
        >
          {{
            building
              ? 'Считаю…'
              : windowsMode
                ? 'Принять'
                : 'Применить решения и утвердить'
          }}
        </button>
        <!-- решать не по кому — утверждаем; подбор прервали или он упал — можно повторить -->
        <button
          v-else-if="preview"
          class="primary"
          :disabled="building"
          @click="emit('approve', decidedPlanId)"
        >
          Утвердить
        </button>
        <button v-else class="primary" :disabled="building || searching" @click="searchWindows">
          {{ searching ? 'Читаю…' : 'Повторить' }}
        </button>
        <!-- подбор уже посчитан: «Отмена» его выбрасывает, и мы возвращаемся к исходному плану -->
        <button class="cancel" :disabled="building || dropping" @click="close">
          {{ dropping ? 'Убираю…' : 'Отмена' }}
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
