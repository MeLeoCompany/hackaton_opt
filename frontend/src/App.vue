<script setup>
// Каркас: без входа — экран входа; после — слева разделы, справа открытая страница.
// День — общий параметр сервиса, его полоса стоит на каждой странице под заголовком.
// Офис полосы не имеет: у диспетчера он из учётки, администратор выбирает его в боковой панели.
import { computed, onMounted, watch } from 'vue'

import AppSidebar from './components/AppSidebar.vue'
import { useAuth } from './composables/useAuth.js'
import { usePlanFocus } from './composables/usePlanFocus.js'
import { useSelectedDay } from './composables/useSelectedDay.js'
import EngineersPage from './pages/EngineersPage.vue'
import EquipmentPage from './pages/EquipmentPage.vue'
import ImportPage from './pages/ImportPage.vue'
import LoginPage from './pages/LoginPage.vue'
import NormsPage from './pages/NormsPage.vue'
import OfficesPage from './pages/OfficesPage.vue'
import PlanComparisonPage from './pages/PlanComparisonPage.vue'
import PlansPage from './pages/PlansPage.vue'
import RequestsPage from './pages/RequestsPage.vue'
import RouteStandPage from './pages/RouteStandPage.vue'
import UsersPage from './pages/UsersPage.vue'

const ALL_SECTIONS = [
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
  {
    key: 'references',
    label: 'Справочники',
    icon: '☷',
    items: [
      { key: 'offices', label: 'Офисы', adminOnly: true },
      { key: 'norms', label: 'Нормативы' },
      { key: 'equipment', label: 'Оборудование' },
      { key: 'users', label: 'Пользователи', adminOnly: true },
    ],
  },
  { key: 'import', label: 'Загрузка CSV (тестовая)', icon: '⇪' },
  { key: 'routes', label: 'Маршруты (тестовые)', icon: '➤' },
]

const TAB_STORAGE_KEY = 'routing.activeTab'
const TABS = [
  'requests', 'engineers', 'plans', 'comparison', 'offices', 'norms', 'equipment', 'users', 'import', 'routes',
]
// вкладка «Справочники» была одной страницей — теперь это «Офисы» внутри раздела
const RENAMED_TABS = { references: 'offices' }

// открытая вкладка переживает перезагрузку страницы: диспетчер обновляет её посреди работы
function storedTab() {
  try {
    const stored = window.localStorage.getItem(TAB_STORAGE_KEY)
    const tab = RENAMED_TABS[stored] ?? stored
    return TABS.includes(tab) ? tab : ''
  } catch {
    return '' // приватное окно или запрещённые куки
  }
}

const { activeTab, openTab } = usePlanFocus()
activeTab.value = storedTab() || 'requests'

const { user, isAdmin, offices, currentOfficeId, currentOfficeName, chooseOffice, logout, restore } = useAuth()

// диспетчеру справочники офисов и учёток не показываются вовсе
const sections = computed(() =>
  ALL_SECTIONS.map((section) =>
    section.items ? { ...section, items: section.items.filter((item) => isAdmin.value || !item.adminOnly) } : section,
  ),
)
const allowedTabs = computed(() =>
  sections.value.flatMap((section) => (section.items ? section.items.map((item) => item.key) : [section.key])),
)

// вкладка из прошлой сессии недоступна новой учётке — открываем заявки
watch(
  [allowedTabs, user],
  () => {
    if (user.value && !allowedTabs.value.includes(activeTab.value)) openTab('requests')
  },
  { immediate: true },
)

const { loadDaysWithRequests, refreshDaysWithRequests } = useSelectedDay()

// вошли или сменили офис — дни с заявками уже другие
watch(currentOfficeId, (officeId, previous) => {
  if (user.value && officeId !== null && officeId !== previous) refreshDaysWithRequests()
})

onMounted(async () => {
  await restore()
  if (user.value) loadDaysWithRequests()
})
</script>

<template>
  <LoginPage v-if="!user" />

  <div v-else class="app">
    <AppSidebar
      :sections="sections"
      :active-tab="activeTab"
      :user="user"
      :is-admin="isAdmin"
      :offices="offices"
      :office-id="currentOfficeId"
      :office-name="currentOfficeName"
      @open="openTab"
      @choose-office="chooseOffice"
      @logout="logout"
    />

    <div class="app-main">
      <!-- сменили офис — страница собирается заново и грузит данные уже этого офиса -->
      <div :key="currentOfficeId ?? 'none'" class="page">
        <RequestsPage v-if="activeTab === 'requests'" />
        <EngineersPage v-else-if="activeTab === 'engineers'" />
        <PlansPage v-else-if="activeTab === 'plans'" />
        <PlanComparisonPage v-else-if="activeTab === 'comparison'" />
        <OfficesPage v-else-if="activeTab === 'offices'" />
        <NormsPage v-else-if="activeTab === 'norms'" />
        <EquipmentPage v-else-if="activeTab === 'equipment'" />
        <UsersPage v-else-if="activeTab === 'users'" />
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
