<script setup>
// Ход расчёта таблицей: уровень, время, сообщение, кто написал. Шаг разворачивается вниз
// прямо в этой же таблице — строки его подробностей встают следующими, без сдвигов,
// чтобы длинный журнал читался колонками (db/init/039).
import { computed, ref } from 'vue'

import { moscowLogTimeOf } from '../utils/moscowTime.js'
import { durationText, worstLevel } from '../utils/runEvents.js'

const props = defineProps({
  nodes: { type: Array, required: true }, // дерево событий: eventTree(run.events)
})

const LEVEL_NAMES = { info: 'инфо', warning: 'важно', error: 'ошибка' }

const open = ref(new Set())

function toggle(node) {
  if (!node.children.length) return
  const next = new Set(open.value)
  if (next.has(node.id)) next.delete(node.id)
  else next.add(node.id)
  open.value = next
}

// плоский список строк в порядке показа: раскрытый шаг сразу продолжается своими строками
const rows = computed(() => {
  const result = []
  const walk = (nodes) => {
    for (const node of nodes) {
      result.push(node)
      if (open.value.has(node.id)) walk(node.children)
    }
  }
  walk(props.nodes)
  return result
})
</script>

<template>
  <!-- ширины колонок заданы жёстко: при раскрытии шага таблица не должна прыгать -->
  <table class="data-table log-table">
    <colgroup>
      <col style="width: 26px" />
      <col style="width: 86px" />
      <col style="width: 104px" />
      <col />
      <col style="width: 108px" />
    </colgroup>
    <thead>
      <tr>
        <!-- раскрывающий значок стоит в своей колонке: иначе он сдвигал бы текст сообщений -->
        <th></th>
        <th>Уровень</th>
        <th>Время</th>
        <th>Сообщение</th>
        <th>Источник</th>
      </tr>
    </thead>
    <tbody>
      <tr
        v-for="node in rows"
        :key="node.id"
        :class="['log-row', worstLevel(node), { branch: node.children.length, opened: open.has(node.id) }]"
        @click="toggle(node)"
      >
        <td class="twist">{{ node.children.length ? (open.has(node.id) ? '▾' : '▸') : '' }}</td>
        <td class="nowrap">
          <span :class="['level', worstLevel(node)]">{{ LEVEL_NAMES[worstLevel(node)] ?? worstLevel(node) }}</span>
        </td>
        <td class="nowrap">{{ moscowLogTimeOf(node.at) }}</td>
        <td>
          <span :class="{ title: node.children.length || node.duration_ms !== null }">{{ node.message }}</span>
          <span v-if="durationText(node)" class="took">· {{ durationText(node) }}</span>
          <span v-if="node.children.length && !open.has(node.id)" class="muted">
            · внутри строк {{ node.children.length }}
          </span>
        </td>
        <td class="nowrap">{{ node.source }}</td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.log-table {
  width: 100%;
  table-layout: fixed;
  font-size: 12px;
}

.log-table td {
  padding: 3px 10px;
}

.log-row.branch {
  cursor: pointer;
}

.log-row.opened td {
  background: #eff6ff;
}

.level {
  display: inline-block;
  min-width: 52px;
  padding: 0 6px;
  border-radius: 4px;
  background: #e2e8f0;
  color: #475569;
  text-align: center;
}

.level.warning {
  background: #fef3c7;
  color: #92400e;
}

.level.error {
  background: #fee2e2;
  color: #b91c1c;
}

.twist {
  padding-right: 0;
  padding-left: 8px;
  color: #94a3b8;
}

.title {
  font-weight: 600;
}

.took,
.muted {
  color: #94a3b8;
}
</style>
