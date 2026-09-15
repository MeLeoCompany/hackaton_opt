<script setup>
// filters — объект фильтров из useEngineersView, поля меняют его напрямую
defineProps({
  filters: { type: Object, required: true },
  references: { type: Object, required: true },
  activeCount: { type: Number, required: true },
})
defineEmits(['reset'])
</script>

<template>
  <section class="filters">
    <div class="filters-header">
      <span>Фильтры</span>
      <button class="link" :disabled="activeCount === 0" @click="$emit('reset')">
        Сбросить{{ activeCount ? ` (${activeCount})` : '' }}
      </button>
    </div>

    <div class="filters-fields">
      <label class="field">
        <span>Поиск</span>
        <input v-model="filters.text" placeholder="Имя или номер" />
      </label>

      <label class="field">
        <span>Транспорт</span>
        <select v-model="filters.transportId">
          <option value="">Любой</option>
          <option v-for="item in references.transports" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
      </label>

      <label class="field">
        <span>Умеет</span>
        <select v-model="filters.skillId">
          <option value="">Любой навык</option>
          <option v-for="item in references.skills" :key="item.id" :value="item.id">{{ item.name }}</option>
        </select>
      </label>
    </div>
  </section>
</template>
