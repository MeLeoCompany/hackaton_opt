<script setup>
import { ref } from 'vue'

import RequestsPage from './pages/RequestsPage.vue'
import RouteStandPage from './pages/RouteStandPage.vue'

const activeTab = ref('requests')
</script>

<template>
  <div class="app">
    <nav class="tabs">
      <span class="brand">Планирование маршрутов</span>
      <button :class="{ active: activeTab === 'requests' }" @click="activeTab = 'requests'">Заявки</button>
      <button :class="{ active: activeTab === 'routes' }" @click="activeTab = 'routes'">
        Маршруты (стенд)
      </button>
    </nav>

    <div class="page">
      <RequestsPage v-if="activeTab === 'requests'" />
      <RouteStandPage v-else />
    </div>
  </div>
</template>

<style>
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  color: #0f172a;
}

input,
select,
button {
  font: inherit;
  font-size: 13px;
}

input,
select {
  padding: 6px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
}

button {
  padding: 6px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
}

button:hover:not(:disabled) {
  border-color: #2563eb;
  color: #2563eb;
}

button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

button.primary {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}

button.primary:hover:not(:disabled) {
  background: #1d4ed8;
  color: #fff;
}

button.danger:hover:not(:disabled) {
  border-color: #dc2626;
  color: #dc2626;
}

/* кнопки действий в строке таблицы: одинаковой ширины, чтобы при переходе
   «Изменить/Удалить» -> «Сохранить/Отмена» колонка не прыгала */
.row-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.row-actions button {
  min-width: 96px;
}

.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 16px;
  height: 46px;
  border-bottom: 1px solid #e2e8f0;
  flex-shrink: 0;
}

.tabs .brand {
  font-weight: 600;
  margin-right: 16px;
}

.tabs button {
  border: none;
  border-radius: 0;
  height: 46px;
  background: none;
  border-bottom: 2px solid transparent;
}

.tabs button.active {
  border-bottom-color: #2563eb;
  color: #2563eb;
}

.page {
  flex: 1;
  min-height: 0;
}
</style>
