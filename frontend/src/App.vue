<script setup>
import { onMounted, ref, watch } from 'vue'

import { useSelectedDay } from './composables/useSelectedDay.js'
import EngineersPage from './pages/EngineersPage.vue'
import ImportPage from './pages/ImportPage.vue'
import PlansPage from './pages/PlansPage.vue'
import RequestsPage from './pages/RequestsPage.vue'
import RouteStandPage from './pages/RouteStandPage.vue'

const TABS = [
  { key: 'requests', label: 'Заявки' },
  { key: 'engineers', label: 'Исполнители' },
  { key: 'plans', label: 'Планы' },
  { key: 'import', label: 'Загрузка CSV' },
  { key: 'routes', label: 'Маршруты (стенд)' },
]

const TAB_STORAGE_KEY = 'routing.activeTab'

// открытая вкладка переживает перезагрузку страницы: диспетчер обновляет её посреди работы
function storedTab() {
  try {
    const stored = window.localStorage.getItem(TAB_STORAGE_KEY)
    return TABS.some((tab) => tab.key === stored) ? stored : ''
  } catch {
    return '' // приватное окно или запрещённые куки
  }
}

const activeTab = ref(storedTab() || 'requests')

watch(activeTab, (tab) => {
  try {
    window.localStorage.setItem(TAB_STORAGE_KEY, tab)
  } catch {
    // не смогли запомнить — вкладка просто не переживёт перезагрузку
  }
})

const { loadDaysWithRequests } = useSelectedDay()
onMounted(loadDaysWithRequests)
</script>

<template>
  <div class="app">
    <nav class="tabs">
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
      <ImportPage v-else-if="activeTab === 'import'" />
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
