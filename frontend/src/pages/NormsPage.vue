<script setup>
// Нормативы типов работ. Администратор правит минуты дороги и работы на месте; это меняет
// только подстановку по умолчанию в новых заявках — у существующих длительность своя.
// Название и навык типа работ заданы ТЗ и не правятся. Диспетчер таблицу только смотрит.
import { computed, onMounted } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import IconButton from '../components/IconButton.vue'
import { useAuth } from '../composables/useAuth.js'
import { useNorms } from '../composables/useNorms.js'
import { referenceName } from '../utils/referenceNames.js'

const {
  references,
  loading,
  saving,
  errorMessage,
  errorDetails,
  noticeMessage,
  editingId,
  form,
  load,
  startEdit,
  cancelEdit,
  saveForm,
} = useNorms()

const { isAdmin } = useAuth()

// базовый норматив в строке правки пересчитывается сразу, как на сервере: дорога + работа
const editedBaseline = computed(() => {
  const total = Number(form.value?.travel_minutes || 0) + Number(form.value?.work_minutes || 0)
  return Number.isFinite(total) ? total : '—'
})

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Нормативы</h1>
      <p>
        Типы работ · время в минутах<template v-if="isAdmin">
          · правка меняет только подстановку в новых заявках</template
        >
      </p>
    </header>

    <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />

    <p v-if="loading" class="muted">Загружаю нормативы…</p>

    <div v-else class="table-scroll">
      <table class="data-table fixed-columns">
        <colgroup>
          <col />
          <col style="width: 240px" />
          <col style="width: 130px" />
          <col style="width: 170px" />
          <col style="width: 195px" />
          <col v-if="isAdmin" style="width: 110px" />
        </colgroup>
        <thead>
          <tr>
            <th>Тип работ</th>
            <th>Навык</th>
            <th>Дорога, мин</th>
            <th>Работа на месте, мин</th>
            <th>Базовый норматив, мин</th>
            <th v-if="isAdmin"></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="workType in references.work_types" :key="workType.id">
            <tr v-if="workType.id === editingId" class="editing">
              <td>{{ workType.name }}</td>
              <td>{{ referenceName(references, 'skills', workType.skill_id) }}</td>
              <td>
                <input v-model="form.travel_minutes" type="number" min="0" max="1440" aria-label="дорога, минут" />
              </td>
              <td>
                <input
                  v-model="form.work_minutes"
                  type="number"
                  min="1"
                  max="1440"
                  aria-label="работа на месте, минут"
                />
              </td>
              <td class="number-cell" title="Дорога + работа на месте">{{ editedBaseline }}</td>
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
              <td>{{ workType.name }}</td>
              <td>{{ referenceName(references, 'skills', workType.skill_id) }}</td>
              <td class="number-cell">{{ workType.travel_minutes }}</td>
              <td class="number-cell">{{ workType.work_minutes }}</td>
              <td class="number-cell">{{ workType.baseline_minutes }}</td>
              <td v-if="isAdmin">
                <div class="row-actions">
                  <IconButton
                    icon="edit"
                    label="Изменить нормативы"
                    :disabled="editingId !== null"
                    @click="startEdit(workType)"
                  />
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>
