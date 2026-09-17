<script setup>
// Каркас: слева разделы, справа открытая страница. День — общий параметр сервиса, его полоса
// стоит на каждой странице под заголовком и работает с одним и тем же выбранным днём.
import { onMounted } from 'vue'

import AppSidebar from './components/AppSidebar.vue'
import { usePlanFocus } from './composables/usePlanFocus.js'
import { useSelectedDay } from './composables/useSelectedDay.js'
import EngineersPage from './pages/EngineersPage.vue'
import ImportPage from './pages/ImportPage.vue'
import PlanComparisonPage from './pages/PlanComparisonPage.vue'
import PlansPage from './pages/PlansPage.vue'
import RequestsPage from './pages/RequestsPage.vue'
import RouteStandPage from './pages/RouteStandPage.vue'

const SECTIONS = [
  { key: 'requests', label: 'Заявки', icon: '▤' },
  { key: 'engineers', label: 'Исполнители', icon: '⚒' },
  {
    key: 'plans',
    label: 'Планы',
    icon: '⚑',
    items: [
      { key: 'plans', label: 'Планы дня' },
      { key: 'comparison', label: 'Сравнение планов' },
    ],
  },
  { key: 'import', label: 'Загрузка CSV (тестовая)', icon: '⇪' },
  { key: 'routes', label: 'Маршруты (тестовые)', icon: '➤' },
]

const TAB_STORAGE_KEY = 'routing.activeTab'
const TABS = ['requests', 'engineers', 'plans', 'comparison', 'import', 'routes']

// открытая вкладка переживает перезагрузку страницы: диспетчер обновляет её посреди работы
function storedTab() {
  try {
    const stored = window.localStorage.getItem(TAB_STORAGE_KEY)
    return TABS.includes(stored) ? stored : ''
  } catch {
    return '' // приватное окно или запрещённые куки
  }
}

const { activeTab, openTab } = usePlanFocus()
activeTab.value = storedTab() || 'requests'

const { loadDaysWithRequests } = useSelectedDay()
onMounted(loadDaysWithRequests)
</script>

<template>
  <div class="app">
    <AppSidebar :sections="SECTIONS" :active-tab="activeTab" @open="openTab" />

    <div class="app-main">
      <div class="page">
        <RequestsPage v-if="activeTab === 'requests'" />
        <EngineersPage v-else-if="activeTab === 'engineers'" />
        <PlansPage v-else-if="activeTab === 'plans'" />
        <PlanComparisonPage v-else-if="activeTab === 'comparison'" />
        <ImportPage v-else-if="activeTab === 'import'" />
        <RouteStandPage v-else />
      </div>
    </div>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  height: 100vh;
}

.app-main {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.page {
  flex: 1;
  min-height: 0;
}
</style>
