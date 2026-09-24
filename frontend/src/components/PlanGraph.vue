<script setup>
// Как расчёты дня выросли друг из друга. Свёрнуто — хвост цепочки: последние расчёты и их
// ветки, чтобы строка не разъезжалась. «Развернуть» показывает всю историю дня целиком
// (docs/algoV2.md, шаг 6).
import { computed, ref } from 'vue'

import { planGraph } from '../utils/planGraph.js'
import { planWindowOf } from '../utils/planWindow.js'
import { moscowTimeOf } from '../utils/moscowTime.js'
import { useSystemTime } from '../composables/useSystemTime.js'
import PlanGraphGrid from './PlanGraphGrid.vue'

const props = defineProps({
  plans: { type: Array, required: true },
  selectedPlanId: { type: Number, default: null },
})
const emit = defineEmits(['select'])

// сколько поколений показывать в строке: дальше начинается горизонтальная прокрутка
const TAIL_COLUMNS = 3

const graph = computed(() => planGraph(props.plans))
const { now } = useSystemTime()
// в строке — хвост цепочки, «Развернуть» открывает всю историю дня окном
const historyOpen = ref(false)

// хвост цепочки: последние поколения и связи между ними. Строки переиндексируем, чтобы
// свёрнутые ветки не оставляли пустых полос
const tail = computed(() => {
  const { nodes, columns } = graph.value
  const from = Math.max(0, columns - TAIL_COLUMNS)
  const visible = nodes.filter((node) => node.col >= from)
  const rows = [...new Set(visible.map((node) => node.row))].sort((a, b) => a - b)
  const rowOf = (node) => rows.indexOf(node.row)
  const shownIds = new Set(visible.map((node) => node.plan.id))
  return {
    nodes: visible.map((node) => {
      const source = visible.find((other) => other.plan.id === node.edge?.fromId)
      return {
        ...node,
        col: node.col - from,
        row: rowOf(node),
        // связь рисуем, только если виден и тот, из чего расчёт вырос
        edge: source ? { ...node.edge, up: rowOf(node) - rowOf(source) } : null,
      }
    }),
    rows: rows.length,
    columns: Math.min(columns, TAIL_COLUMNS),
    hidden: nodes.length - shownIds.size,
  }
})

// чем расчёт кончился или что с ним будет — коротко, подробности в подсказке. Срок берём там
// же, где его берёт таблица, иначе в графе и в строке было бы написано разное
function openPlan(planId) {
  historyOpen.value = false
  emit('select', planId)
}

function state(summary) {
  if (summary.superseded_at) return { text: `до ${moscowTimeOf(summary.superseded_at)}`, cls: 'past' }
  if (summary.approved_at) return { text: 'действует', cls: 'live' }
  if (summary.voided_at) {
    return { text: 'не вступил в силу', cls: 'failed', title: summary.void_reason ?? '' }
  }
  const window = planWindowOf(summary, now.value)
  if (window?.state === 'expired') {
    return { text: 'не вступит в силу', cls: 'failed', title: window.title }
  }
  if (window && summary.replanned_at) {
    return { text: `в силу в ${moscowTimeOf(summary.replanned_at)}`, cls: 'draft', title: window.title }
  }
  if (window) {
    return { text: `до ${moscowTimeOf(summary.effective_at)}`, cls: 'draft', title: window.title }
  }
  if (summary.outdated) return { text: 'неактуален', cls: 'past' }
  return { text: 'черновик', cls: 'draft' }
}


</script>

<template>
  <div v-if="graph.nodes.length > 1" class="graph-line">
    <div class="graph-scroll">
      <PlanGraphGrid
        :graph="tail"
        :state="state"
        :selected-plan-id="selectedPlanId"
        @select="emit('select', $event)"
      />
    </div>
    <button
      class="link expand"
      :title="
        tail.hidden
          ? `Показать всю историю дня: ещё ${tail.hidden} расчётов и их ветки`
          : 'Показать всю историю дня отдельным окном'
      "
      @click="historyOpen = true"
    >
      Развернуть{{ tail.hidden ? ` · ещё ${tail.hidden}` : '' }}
    </button>

    <div v-if="historyOpen" class="dialog-backdrop" @click.self="historyOpen = false">
      <div class="dialog" role="dialog" aria-label="История расчётов дня">
        <header>
          <strong>История расчётов дня</strong>
          <button class="close" title="Закрыть" @click="historyOpen = false">×</button>
        </header>
        <p class="hint">
          Слева первый расчёт, вправо — во что он превратился. Прямая линия ведёт к действующему
          плану, ветка вниз — то, что пошло в сторону: пересчёт, не вступивший в силу, или
          черновик, который не утвердили. Номер открывает расчёт.
        </p>
        <div class="history-scroll">
          <PlanGraphGrid
            :graph="graph"
            :state="state"
            :selected-plan-id="selectedPlanId"
            @select="openPlan"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.graph-line {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  margin-bottom: 8px;
  font-size: 12px;
}

/* на узком экране прокручивается сам граф, а не страница */
.graph-scroll {
  flex: 1 1 auto;
  min-width: 0;
  overflow-x: auto;
  padding-bottom: 2px;
}

/* кнопка уходит к правому краю и стоит в одну строку с первым рядом узлов */
.expand {
  flex: none;
  margin-left: auto;
  color: #64748b;
  font-size: 12px;
  line-height: 30px;
  white-space: nowrap;
}

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
  width: min(1400px, 96vw);
  max-height: 88vh;
  padding: 14px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(15 23 42 / 30%);
}

.dialog header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
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

/* большая развилка может не влезть и в окно: там прокрутка уместна */
.history-scroll {
  overflow: auto;
  padding: 4px 2px;
}
</style>
