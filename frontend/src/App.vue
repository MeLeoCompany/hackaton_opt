<script setup>
import { ref } from 'vue'

import EngineersPage from './pages/EngineersPage.vue'
import PlansPage from './pages/PlansPage.vue'
import RequestsPage from './pages/RequestsPage.vue'
import RouteStandPage from './pages/RouteStandPage.vue'

const TABS = [
  { key: 'requests', label: 'Заявки' },
  { key: 'engineers', label: 'Исполнители' },
  { key: 'plans', label: 'Планы' },
  { key: 'routes', label: 'Маршруты (стенд)' },
]

const activeTab = ref('requests')
</script>

<template>
  <div class="app">
    <nav class="tabs">
      <span class="brand">Планирование маршрутов</span>
      <button
        v-for="tab in TABS"
        :key="tab.key"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </nav>

    <div class="page">
      <RequestsPage v-if="activeTab === 'requests'" />
      <EngineersPage v-else-if="activeTab === 'engineers'" />
      <PlansPage v-else-if="activeTab === 'plans'" />
      <RouteStandPage v-else />
    </div>
  </div>
</template>

<style scoped>
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

.brand {
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
