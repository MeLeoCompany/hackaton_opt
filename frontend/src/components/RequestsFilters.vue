<script setup>
import { NO_TRANSPORT } from '../composables/useRequestsView.js'
import { formatDay } from '../utils/moscowTime.js'

// filters — объект фильтров из useRequestsView, поля меняют его напрямую
defineProps({
  filters: { type: Object, required: true },
  references: { type: Object, required: true },
  availableDays: { type: Array, required: true },
  activeCount: { type: Number, required: true },
})
defineEmits(['reset'])
</script>

<template>
  <section class="filters">
    <label class="field">
      <span>Планирование</span>
      <select v-model="filters.activity">
        <option value="">Все заявки</option>
        <option value="active">Только активные</option>
        <option value="inactive">Только выключенные</option>
      </select>
    </label>

    <label class="field search">
      <span>Поиск</span>
      <input v-model="filters.text" placeholder="Номер или адрес" />
    </label>

    <label class="field">
      <span>Приоритет</span>
      <select v-model="filters.priorityId">
        <option value="">Любой</option>
        <option v-for="item in references.priorities" :key="item.id" :value="item.id">{{ item.name }}</option>
      </select>
    </label>

    <label class="field">
      <span>Навык</span>
      <select v-model="filters.skillId">
        <option value="">Любой</option>
        <option v-for="item in references.skills" :key="item.id" :value="item.id">{{ item.name }}</option>
      </select>
    </label>

    <label class="field">
      <span>Транспорт</span>
      <select v-model="filters.transportId">
        <option value="">Любой</option>
        <option :value="NO_TRANSPORT">Не важен</option>
        <option v-for="item in references.transports" :key="item.id" :value="item.id">{{ item.name }}</option>
      </select>
    </label>

    <label class="field">
      <span>День</span>
      <select v-model="filters.day">
        <option value="">Любой</option>
        <option v-for="day in availableDays" :key="day" :value="day">{{ formatDay(day) }}</option>
      </select>
    </label>

    <div class="field">
      <span>Окно начинается (МСК)</span>
      <div class="time-range">
        <input v-model="filters.timeFrom" type="time" aria-label="не раньше" />
        <span>—</span>
        <input v-model="filters.timeTo" type="time" aria-label="не позже" />
      </div>
    </div>

    <button class="reset" :disabled="activeCount === 0" @click="$emit('reset')">
      Сбросить{{ activeCount ? ` (${activeCount})` : '' }}
    </button>
  </section>
</template>

<style scoped>
.filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 10px 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #64748b;
}

.field select {
  min-width: 150px;
}

.search input {
  width: 220px;
}

.time-range {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
