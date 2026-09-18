<script setup>
// Нормативы ТЗ: типы работ со временем дороги и работы на месте. Только для сверки —
// значения заданы ТЗ и в интерфейсе не правятся.
import { onMounted, ref } from 'vue'

import { fetchReferences } from '../api/referencesApi.js'
import { useMessages } from '../composables/useMessages.js'
import { referenceName } from '../utils/referenceNames.js'

const references = ref({ skills: [], priorities: [], transports: [], work_types: [] })
const loading = ref(false)
const { errorMessage, showError } = useMessages()

onMounted(async () => {
  loading.value = true
  try {
    references.value = await fetchReferences()
  } catch (error) {
    showError(error)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Нормативы</h1>
      <p>Типы работ по ТЗ · время в минутах</p>
    </header>

    <div v-if="errorMessage" class="message error">
      <strong>{{ errorMessage }}</strong>
    </div>

    <p v-if="loading" class="muted">Загружаю нормативы…</p>

    <div v-else class="table-scroll">
      <table class="data-table">
        <thead>
          <tr>
            <th>Тип работ</th>
            <th>Навык</th>
            <th>Дорога, мин</th>
            <th>Работа на месте, мин</th>
            <th>Базовый норматив, мин</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="workType in references.work_types" :key="workType.id">
            <td>{{ workType.name }}</td>
            <td>{{ referenceName(references, 'skills', workType.skill_id) }}</td>
            <td class="number-cell">{{ workType.travel_minutes }}</td>
            <td class="number-cell">{{ workType.work_minutes }}</td>
            <td class="number-cell">{{ workType.baseline_minutes }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
