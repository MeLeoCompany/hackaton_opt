<script setup>
// Справочник оборудования: что техник привозит на заявку. Требование ставится в заявке
// (колонка «Тип работ» на вкладке заявок). Тип, который требуют заявки, не удалить.
import { computed, onMounted, ref } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import IconButton from '../components/IconButton.vue'
import { useAuth } from '../composables/useAuth.js'
import { NEW_EQUIPMENT, useEquipment } from '../composables/useEquipment.js'
import { listCapacity, saveCapacity } from '../api/equipmentApi.js'

const {
  equipment,
  loading,
  saving,
  errorMessage,
  errorDetails,
  noticeMessage,
  editingId,
  form,
  load,
  startCreate,
  startEdit,
  cancelEdit,
  saveForm,
  remove,
} = useEquipment()

// справочник правит администратор; диспетчер его только смотрит
const { isAdmin } = useAuth()

// Ёмкость: сколько штук бригада увезёт на своём транспорте. По ней считается выдача
// оборудования по плану — больше предела диспетчер выписать не сможет.
const capacityRows = ref([])
const limits = ref({})
const savingCapacity = ref(false)
const capacityNotice = ref('')

const key = (transportId, equipmentId) => `${transportId}:${equipmentId}`

// из плоского списка пар делаем сетку: строки — транспорт, колонки — оборудование
const transportRows = computed(() => {
  const seen = new Map()
  for (const row of capacityRows.value) {
    if (!seen.has(row.transport_id)) seen.set(row.transport_id, row.transport_name)
  }
  return [...seen].map(([id, name]) => ({ id, name }))
})

const equipmentColumns = computed(() => {
  const seen = new Map()
  for (const row of capacityRows.value) {
    if (!seen.has(row.equipment_id)) seen.set(row.equipment_id, row.equipment_name)
  }
  return [...seen].map(([id, name]) => ({ id, name }))
})

async function loadCapacity() {
  try {
    capacityRows.value = await listCapacity()
    limits.value = Object.fromEntries(
      capacityRows.value.map((row) => [key(row.transport_id, row.equipment_id), row.max_quantity]),
    )
  } catch (error) {
    errorMessage.value = error.message
  }
}

async function storeCapacity() {
  savingCapacity.value = true
  capacityNotice.value = ''
  try {
    const rows = capacityRows.value.map((row) => ({
      transport_id: row.transport_id,
      equipment_id: row.equipment_id,
      max_quantity: Number(limits.value[key(row.transport_id, row.equipment_id)]) || 0,
    }))
    capacityRows.value = await saveCapacity(rows)
    capacityNotice.value = 'Пределы сохранены'
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    savingCapacity.value = false
  }
}

onMounted(() => {
  load()
  loadCapacity()
})
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Оборудование</h1>
      <p>Всего {{ equipment.length }} · что техник привозит на заявку</p>
    </header>

    <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />

    <p v-if="loading" class="muted">Загружаю оборудование…</p>

    <template v-else>
      <div v-if="isAdmin" class="list-bar">
        <button class="primary" :disabled="editingId !== null" @click="startCreate">+ Добавить оборудование</button>
      </div>

      <div class="table-scroll">
        <table class="data-table fixed-columns">
          <colgroup>
            <col style="width: 70px" />
            <col style="width: 220px" />
            <col />
            <col style="width: 110px" />
            <col style="width: 110px" />
            <col style="width: 110px" />
          </colgroup>
          <thead>
            <tr>
              <th>№</th>
              <th>Название</th>
              <th>Описание</th>
              <th>Заявок</th>
              <th>У бригад</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <template
              v-for="item in [...equipment, ...(editingId === NEW_EQUIPMENT ? [null] : [])]"
              :key="item?.id ?? 'new'"
            >
              <tr v-if="item === null || item.id === editingId" class="editing">
                <td class="number-cell">{{ item?.id ?? '—' }}</td>
                <td><input v-model="form.name" placeholder="Роутер" aria-label="название оборудования" /></td>
                <td>
                  <input v-model="form.description" placeholder="для чего нужно" aria-label="описание оборудования" />
                </td>
                <td class="number-cell">{{ item?.request_count ?? 0 }}</td>
                <td class="number-cell">{{ item?.engineer_count ?? 0 }}</td>
                <td>
                  <div class="row-actions">
                    <IconButton
                      icon="save"
                      :label="saving ? 'Сохраняю…' : 'Сохранить'"
                      variant="primary"
                      :disabled="saving"
                      @click="saveForm"
                    />
                    <IconButton icon="cancel" label="Отмена" :disabled="saving" @click="cancelEdit" />
                  </div>
                </td>
              </tr>

              <tr v-else>
                <td class="number-cell">{{ item.id }}</td>
                <td><strong>{{ item.name }}</strong></td>
                <td class="muted">{{ item.description || '—' }}</td>
                <td class="number-cell">{{ item.request_count }}</td>
                <td class="number-cell">{{ item.engineer_count }}</td>
                <td>
                  <div v-if="isAdmin" class="row-actions">
                    <IconButton icon="edit" label="Изменить" :disabled="editingId !== null" @click="startEdit(item)" />
                    <IconButton
                      icon="delete"
                      variant="danger"
                      :label="item.request_count || item.engineer_count ? `Есть в заявках (${item.request_count}) и у бригад (${item.engineer_count}) — не удалить` : 'Удалить'"
                      :disabled="editingId !== null || saving || item.request_count > 0 || item.engineer_count > 0"
                      @click="remove(item)"
                    />
                  </div>
                </td>
              </tr>
            </template>

            <tr v-if="!equipment.length && editingId !== NEW_EQUIPMENT">
              <td colspan="6" class="empty">Оборудования в справочнике нет</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2 class="section-title">Сколько увозит бригада</h2>
      <p class="muted section-note">
        Предел выдачи на один выезд: по нему считается, сколько оборудования выдать бригаде
        под её план — <strong>min(предел, нужно по плану + запас)</strong>. Запас общий,
        он задаётся в «Система» → «Состояние».
      </p>
      <div class="table-scroll">
        <table class="data-table fixed-columns">
          <colgroup>
            <col style="width: 220px" />
            <col v-for="column in equipmentColumns" :key="column.id" style="width: 160px" />
          </colgroup>
          <thead>
            <tr>
              <th>Транспорт</th>
              <th v-for="column in equipmentColumns" :key="column.id">{{ column.name }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in transportRows" :key="row.id">
              <td><strong>{{ row.name }}</strong></td>
              <td v-for="column in equipmentColumns" :key="column.id" class="number-cell">
                <input
                  v-if="isAdmin"
                  v-model="limits[`${row.id}:${column.id}`]"
                  type="number"
                  min="0"
                  class="limit-input"
                  :disabled="savingCapacity"
                  :aria-label="`${row.name}: сколько увезёт (${column.name})`"
                />
                <template v-else>{{ limits[`${row.id}:${column.id}`] ?? 0 }}</template>
              </td>
            </tr>
            <tr v-if="!transportRows.length">
              <td :colspan="equipmentColumns.length + 1" class="empty">Справочник ёмкости пуст</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="isAdmin" class="muted">
        <button class="primary" :disabled="savingCapacity" @click="storeCapacity">
          {{ savingCapacity ? 'Сохраняю…' : 'Сохранить пределы' }}
        </button>
        <span v-if="capacityNotice" class="saved">{{ capacityNotice }}</span>
      </p>
    </template>

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>

<style scoped>
.section-title {
  margin: 18px 0 8px;
  font-size: 15px;
}

.section-note {
  max-width: 720px;
  margin: 0 0 10px;
}

/* поле предела: числа короткие, широкое поле выглядело бы пустым */
.limit-input {
  width: 80px;
  padding: 4px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  text-align: right;
}

.saved {
  margin-left: 10px;
  color: #166534;
  font-size: 12px;
}
</style>
