<script setup>
// Сетка графа: узлы по колонкам (поколение) и строкам (ветка), связи линиями с подписью.
// Раскладку считает planGraph, состояние узла — тот, кто эту сетку показывает.
defineProps({
  graph: { type: Object, required: true }, // {nodes, rows, columns}
  state: { type: Function, required: true }, // что писать на узле: {text, cls, title}
  selectedPlanId: { type: Number, default: null },
})
defineEmits(['select'])

const ROW_HEIGHT = 30
</script>

<template>
  <div
    class="plan-graph"
    :style="{ gridTemplateColumns: `repeat(${graph.columns}, max-content)`, gridAutoRows: `${ROW_HEIGHT}px` }"
  >
    <div
      v-for="node in graph.nodes"
      :key="node.plan.id"
      class="node"
      :style="{ gridColumn: node.col + 1, gridRow: node.row + 1 }"
    >
      <!-- связь с тем, из чего вырос: прямая по строке или уголок с ветки выше -->
      <span
        v-if="node.edge"
        :class="['edge', { branch: node.edge.up > 0 }]"
        :style="node.edge.up > 0 ? { '--up': `${node.edge.up * ROW_HEIGHT}px` } : null"
      >
        <span class="edge-label">{{ node.edge.label }}</span>
      </span>
      <button
        :class="['chip', state(node.plan).cls, { current: node.plan.id === selectedPlanId }]"
        :title="state(node.plan).title || `Открыть расчёт №${node.plan.id}`"
        @click="$emit('select', node.plan.id)"
      >
        №{{ node.plan.id }}
        <span class="chip-state">{{ state(node.plan).text }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.plan-graph {
  display: grid;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
}

.node {
  display: flex;
  align-items: center;
  height: 100%;
}

/* прямая связь: линия с подписью между соседними расчётами */
.edge {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 96px;
  height: 100%;
  padding: 0 6px;
  color: #94a3b8;
}

.edge::before {
  position: absolute;
  top: 50%;
  right: 0;
  left: 0;
  border-top: 1px solid #cbd5e1;
  content: '';
}

/* ветка вниз: уголок от строки, где стоит источник, к строке этого расчёта */
.edge.branch::before {
  top: calc(50% - var(--up));
  left: 6px;
  height: var(--up);
  border-bottom: 1px solid #cbd5e1;
  border-left: 1px solid #cbd5e1;
  border-top: 0;
  border-bottom-left-radius: 8px;
}

.edge-label {
  position: relative;
  padding: 0 4px;
  background: #fff;
  white-space: nowrap;
}

.chip {
  /* одинаковая ширина у всех: иначе развилка выглядит рваной */
  display: inline-flex;
  align-items: baseline;
  justify-content: center;
  width: 180px;
  gap: 5px;
  padding: 2px 8px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #fff;
  color: #1d4ed8;
  font-size: 12px;
  line-height: 1.5;
  white-space: nowrap;
  cursor: pointer;
}

.chip:hover {
  border-color: #93c5fd;
}

.chip.current {
  border-color: #2563eb;
  font-weight: 700;
}

.chip-state {
  overflow: hidden;
  color: #64748b;
  font-size: 11px;
  text-overflow: ellipsis;
}

.chip.live {
  border-color: #bbf7d0;
  background: #dcfce7;
}

.chip.live .chip-state {
  color: #166534;
}

.chip.failed {
  border-color: #fecaca;
  background: #fee2e2;
}

.chip.failed .chip-state {
  color: #991b1b;
}

.chip.past {
  background: #f8fafc;
}
</style>
