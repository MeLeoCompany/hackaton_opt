<script setup>
import { computed } from 'vue'

import { PAGE_SIZES } from '../composables/useRequestsView.js'

const props = defineProps({
  page: { type: Number, required: true },
  pageCount: { type: Number, required: true },
  pageSize: { type: Number, required: true },
  total: { type: Number, required: true },
})
const emit = defineEmits(['update:page', 'update:pageSize'])

const firstShown = computed(() => (props.total === 0 ? 0 : (props.page - 1) * props.pageSize + 1))
const lastShown = computed(() => Math.min(props.page * props.pageSize, props.total))
</script>

<template>
  <nav class="pagination">
    <span class="range">Показано {{ firstShown }}–{{ lastShown }} из {{ total }}</span>

    <div class="pages">
      <button :disabled="page <= 1" title="Первая страница" @click="emit('update:page', 1)">«</button>
      <button :disabled="page <= 1" title="Предыдущая" @click="emit('update:page', page - 1)">‹</button>
      <span class="current">Страница {{ page }} из {{ pageCount }}</span>
      <button :disabled="page >= pageCount" title="Следующая" @click="emit('update:page', page + 1)">›</button>
      <button :disabled="page >= pageCount" title="Последняя страница" @click="emit('update:page', pageCount)">
        »
      </button>
    </div>

    <label class="size">
      По
      <select :value="pageSize" @change="emit('update:pageSize', Number($event.target.value))">
        <option v-for="size in PAGE_SIZES" :key="size" :value="size">{{ size }}</option>
      </select>
      на странице
    </label>
  </nav>
</template>

<style scoped>
.pagination {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
  color: #475569;
}

.pages {
  display: flex;
  align-items: center;
  gap: 4px;
}

.pages button {
  min-width: 34px;
  padding: 5px 8px;
}

.current {
  padding: 0 8px;
  white-space: nowrap;
}

.size {
  display: flex;
  align-items: center;
  gap: 6px;
}
</style>
