<script setup>
// Статус заявки цветной плашкой одной ширины у всех статусов, рядом — значок истории.
// Клик по плашке — список «→ статус», куда оператор может перевести заявку (ручные
// переходы из таблицы переходов; пояснение перехода — подсказкой при наведении).
// Заявка закреплена за утверждённым планом — в списке и переход к ней на карте плана.
// Список открывается поверх страницы (Teleport): ячейка таблицы его не обрезает.
import { computed, nextTick, onBeforeUnmount, ref } from 'vue'

import { referenceName } from '../utils/referenceNames.js'
import { manualTransitions, statusCode } from '../utils/requestStatuses.js'

const props = defineProps({
  statusId: { type: Number, required: true },
  references: { type: Object, required: true },
  // только показать: строка в правке, новая заявка
  readonly: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  withHistory: { type: Boolean, default: true },
  // утверждённый план заявки: пункт «Открыть в плане»
  planId: { type: Number, default: null },
  // в самом плане ссылка «Открыть в плане» не нужна
  withPlanLink: { type: Boolean, default: true },
})
const emit = defineEmits(['change', 'history', 'open-plan'])

const MENU_WIDTH = 220

const open = ref(false)
const trigger = ref(null)
const panel = ref(null)
const position = ref({ top: 0, left: 0 })

const name = computed(() => referenceName(props.references, 'request_statuses', props.statusId))
const code = computed(() => statusCode(props.references, props.statusId))
const transitions = computed(() => manualTransitions(props.references, props.statusId))

// переходов руками нет — объясняем почему и что делать
const noTransitionsText = computed(() => {
  if (code.value === 'cancelled') return 'Отмена окончательна. Чтобы снова выполнить работу — сделайте копию заявки (кнопка в строке)'
  if (code.value === 'done') return 'Заявка выполнена — статус окончательный'
  return 'Статус сменится сам — при утверждении плана или синхронизации'
})

function onOutsideClick(event) {
  if (panel.value?.contains(event.target) || trigger.value?.contains(event.target)) return
  close()
}

async function openPanel() {
  const box = trigger.value.getBoundingClientRect()
  // у правого края окна список сдвигается влево, чтобы не уйти за экран
  position.value = { top: box.bottom + 2, left: Math.min(box.left, window.innerWidth - MENU_WIDTH - 10) }
  open.value = true
  await nextTick()
  // у нижних строк под плашкой места нет — открываем список над ней
  const height = panel.value.offsetHeight
  if (box.bottom + 2 + height > window.innerHeight) position.value.top = Math.max(4, box.top - 2 - height)
  document.addEventListener('mousedown', onOutsideClick, true)
  window.addEventListener('scroll', close, true)
  window.addEventListener('resize', close)
}

function close() {
  open.value = false
  document.removeEventListener('mousedown', onOutsideClick, true)
  window.removeEventListener('scroll', close, true)
  window.removeEventListener('resize', close)
}

function pick(toStatusId) {
  close()
  emit('change', toStatusId)
}

function openPlan() {
  close()
  emit('open-plan', props.planId)
}

onBeforeUnmount(close)
</script>

<template>
  <span class="status-cell">
    <span v-if="readonly" :class="['status-badge', 'status-fixed', `status-${code}`]">{{ name }}</span>
    <button
      v-else
      ref="trigger"
      type="button"
      :class="['status-badge', 'status-fixed', 'status-trigger', `status-${code}`]"
      :disabled="disabled"
      :aria-expanded="open"
      aria-haspopup="menu"
      title="Сменить статус"
      @click.stop="open ? close() : openPanel()"
      @dblclick.stop
    >
      <span class="status-name">{{ name }}</span><span class="status-arrow" aria-hidden="true">▾</span>
    </button>

    <button
      v-if="withHistory && !readonly"
      type="button"
      class="history-button"
      title="История изменений статуса"
      aria-label="История изменений статуса"
      @click.stop="emit('history')"
      @dblclick.stop
    >
      <svg
        viewBox="0 0 24 24"
        width="15"
        height="15"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M3 12a9 9 0 1 0 2.6-6.4L3 8M3 3v5h5M12 7v5l3 2" />
      </svg>
    </button>
  </span>

  <Teleport to="body">
    <div
      v-if="open"
      ref="panel"
      class="status-menu"
      role="menu"
      :style="{ top: `${position.top}px`, left: `${position.left}px`, width: `${MENU_WIDTH}px` }"
      @keydown.esc="close"
      @click.stop
      @dblclick.stop
    >
      <button
        v-for="transition in transitions"
        :key="transition.to_status_id"
        type="button"
        role="menuitem"
        class="status-option"
        :title="transition.description"
        @click="pick(transition.to_status_id)"
      >
        <span class="option-arrow" aria-hidden="true">→</span>
        <span :class="['status-badge', 'status-fixed', `status-${statusCode(references, transition.to_status_id)}`]">
          {{ transition.name }}
        </span>
      </button>
      <p v-if="!transitions.length" class="status-empty">{{ noTransitionsText }}</p>
      <button
        v-if="planId !== null && withPlanLink"
        type="button"
        role="menuitem"
        class="status-option plan-option"
        title="Открыть утверждённый план на карте: маршрут бригады и эта заявка на нём"
        @click="openPlan"
      >
        Открыть в плане №{{ planId }} →
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
.status-cell {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  vertical-align: middle;
}

.status-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  border: 0;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}

.status-trigger:hover:not(:disabled) {
  filter: brightness(0.95);
  box-shadow: 0 0 0 1px rgb(15 23 42 / 15%);
}

.status-trigger:disabled {
  cursor: default;
}

.status-trigger:disabled .status-arrow {
  visibility: hidden;
}

.status-name {
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-arrow {
  flex-shrink: 0;
  font-size: 10px;
  opacity: 0.7;
}

/* значок истории — без рамки, чтобы не спорить с плашкой статуса */
.history-button {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 22px;
  min-width: 0;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
}

.history-button:hover {
  background: #eff6ff;
  color: #1d4ed8;
}

.status-menu {
  position: fixed;
  z-index: 1500;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 8px 24px rgb(15 23 42 / 16%);
  font-size: 13px;
}

.status-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #0f172a;
  text-align: left;
  white-space: normal;
  cursor: pointer;
}

.status-option:hover {
  background: #eff6ff;
}

.option-arrow {
  color: #94a3b8;
}

.plan-option {
  margin-top: 2px;
  border-top: 1px solid #e2e8f0;
  border-radius: 0 0 6px 6px;
  color: #1d4ed8;
}

.status-empty {
  margin: 0;
  padding: 6px 8px;
  color: #64748b;
  font-size: 12px;
}
</style>
