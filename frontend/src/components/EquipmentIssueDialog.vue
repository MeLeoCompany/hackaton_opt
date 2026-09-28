<script setup>
// Выдача оборудования под план: сколько взять каждой бригаде.
// Система предлагает min(сколько увезёт, нужно по плану + запас), диспетчер правит числа
// и утверждает — только тогда они уходят в запас смен, и от него считают пересчёты.
import { computed, onMounted, ref } from 'vue'

import { fetchPlanEquipment, issuePlanEquipment } from '../api/plansApi.js'

const props = defineProps({
  planId: { type: Number, required: true },
})
const emit = defineEmits(['issued', 'close'])

const preview = ref(null)
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref('')
// правки диспетчера: { `бригада:оборудование`: число }
const edits = ref({})

const key = (engineerId, equipmentId) => `${engineerId}:${equipmentId}`

// колонки — типы оборудования: они одинаковы у всех бригад
const columns = computed(() => {
  const first = preview.value?.brigades?.[0]
  return first ? first.items.map((item) => ({ id: item.equipment_id, name: item.equipment_name })) : []
})

const total = computed(() =>
  Object.values(edits.value).reduce((sum, value) => sum + (Number(value) || 0), 0),
)

// красным — если диспетчер выписал больше, чем бригада увезёт: сервер такое не примет
function overLimit(brigade, item) {
  return (Number(edits.value[key(brigade.engineer_id, item.equipment_id)]) || 0) > item.capacity
}

const blocked = computed(() =>
  (preview.value?.brigades ?? []).some((brigade) => brigade.items.some((item) => overLimit(brigade, item))),
)

async function load() {
  loading.value = true
  try {
    preview.value = await fetchPlanEquipment(props.planId)
    edits.value = Object.fromEntries(
      preview.value.brigades.flatMap((brigade) =>
        brigade.items.map((item) => [key(brigade.engineer_id, item.equipment_id), item.recommended]),
      ),
    )
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    loading.value = false
  }
}

// вернуть рекомендацию: после ручных правок бывает нужно начать заново
function reset() {
  for (const brigade of preview.value.brigades) {
    for (const item of brigade.items) {
      edits.value[key(brigade.engineer_id, item.equipment_id)] = item.recommended
    }
  }
}

async function approve() {
  saving.value = true
  errorMessage.value = ''
  try {
    const brigades = preview.value.brigades.map((brigade) => ({
      engineer_id: brigade.engineer_id,
      items: brigade.items.map((item) => ({
        equipment_id: item.equipment_id,
        quantity: Number(edits.value[key(brigade.engineer_id, item.equipment_id)]) || 0,
      })),
    }))
    const done = await issuePlanEquipment(props.planId, brigades)
    emit('issued', done)
  } catch (error) {
    errorMessage.value = [error.message, ...(error.details ?? [])].join(': ')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="dialog-backdrop" @click.self="emit('close')">
    <div class="dialog" role="dialog" aria-label="Выдача оборудования по плану">
      <header>
        <strong>Выдача оборудования · план №{{ planId }}</strong>
        <button class="close" title="Закрыть" @click="emit('close')">×</button>
      </header>

      <p v-if="loading" class="muted">Считаю, что нужно бригадам…</p>
      <p v-else-if="errorMessage" class="error">{{ errorMessage }}</p>

      <template v-if="preview">
        <p class="muted">
          «Нужно» — сколько требуют заявки бригады в этом плане, «увезёт» — предел её транспорта
          из справочника. Предлагается нужное плюс запас {{ preview.reserve }} шт, но не больше предела.
        </p>

        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th rowspan="2">Бригада</th>
                <th rowspan="2">Заявок</th>
                <th v-for="column in columns" :key="column.id" colspan="3">{{ column.name }}</th>
              </tr>
              <tr>
                <template v-for="column in columns" :key="column.id">
                  <th class="sub">нужно</th>
                  <th class="sub">увезёт</th>
                  <th class="sub">выдать</th>
                </template>
              </tr>
            </thead>
            <tbody>
              <tr v-for="brigade in preview.brigades" :key="brigade.engineer_id">
                <td>
                  <strong>{{ brigade.name }}</strong>
                  <span class="muted transport"> · {{ brigade.transport_name }}</span>
                </td>
                <td class="number-cell">{{ brigade.requests }}</td>
                <template v-for="item in brigade.items" :key="item.equipment_id">
                  <td class="number-cell">{{ item.needed }}</td>
                  <td class="number-cell muted">{{ item.capacity }}</td>
                  <td class="number-cell">
                    <input
                      v-model="edits[`${brigade.engineer_id}:${item.equipment_id}`]"
                      type="number"
                      min="0"
                      :max="item.capacity"
                      :class="['issue-input', { over: overLimit(brigade, item) }]"
                      :disabled="saving"
                      :aria-label="`${brigade.name}: выдать ${item.equipment_name}`"
                    />
                  </td>
                </template>
              </tr>
              <tr v-if="!preview.brigades.length">
                <td :colspan="2 + columns.length * 3" class="empty">В этом дне нет смен</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>

      <footer>
        <span class="muted">
          <template v-if="preview">Всего к выдаче {{ total }} шт</template>
        </span>
        <span class="buttons">
          <button v-if="preview" :disabled="saving" @click="reset">Вернуть рекомендацию</button>
          <button
            class="primary"
            :disabled="loading || saving || blocked || !preview?.brigades.length"
            :title="blocked ? 'Где-то выписано больше, чем бригада увезёт' : ''"
            @click="approve"
          >
            {{ saving ? 'Записываю…' : 'Утвердить выдачу' }}
          </button>
          <button :disabled="saving" @click="emit('close')">Отмена</button>
        </span>
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
  width: min(900px, 94vw);
  max-height: 88vh;
  padding: 14px;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(15 23 42 / 30%);
}

.dialog header,
.dialog footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.table-scroll {
  overflow: auto;
}

th.sub {
  font-weight: 400;
  font-size: 12px;
}

.transport {
  font-size: 12px;
}

/* поле короткое: выдают штуки, а не тысячи */
.issue-input {
  width: 64px;
  padding: 3px 6px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  text-align: right;
}

.issue-input.over {
  border-color: #b91c1c;
  background: #fef2f2;
}

.error {
  margin: 0;
  color: #b91c1c;
  font-size: 13px;
}

.buttons {
  display: flex;
  gap: 8px;
}

.close {
  border: none;
  background: none;
  color: #64748b;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}
</style>
