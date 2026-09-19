<script setup>
// Боковая панель разделов: свёрнутая показывает значки, по клику по кнопке разъезжается
// с подписями. Клик по пункту — переход, на узком экране панель сразу сворачивается.
// Разделы с подпунктами (планы, справочники) раскрываются по клику на сам раздел — стрелка
// справа показывает, раскрыт ли он. Раздел открытой страницы раскрыт сразу.
import { ref } from 'vue'

const props = defineProps({
  sections: { type: Array, required: true }, // [{ key, label, icon, items? }]
  activeTab: { type: String, required: true },
  user: { type: Object, required: true },
  isAdmin: { type: Boolean, required: true },
  offices: { type: Array, default: () => [] },
  officeId: { type: Number, default: null },
  officeName: { type: String, default: '' },
})
const emit = defineEmits(['open', 'choose-office', 'logout'])

const STORAGE_KEY = 'routing.sidebarExpanded'

function storedExpanded() {
  try {
    return window.localStorage.getItem(STORAGE_KEY) !== 'no'
  } catch {
    return true // приватное окно или запрещённые куки
  }
}

const expanded = ref(storedExpanded())

function toggle() {
  expanded.value = !expanded.value
  try {
    window.localStorage.setItem(STORAGE_KEY, expanded.value ? 'yes' : 'no')
  } catch {
    // не смогли запомнить — панель просто не переживёт перезагрузку
  }
}

// раскрытые разделы с подпунктами
const openSections = ref(
  new Set(
    props.sections
      .filter((section) => section.items?.some((item) => item.key === props.activeTab))
      .map((section) => section.key),
  ),
)

function toggleSection(section) {
  if (!expanded.value) {
    // в свёрнутой панели подписей нет: разворачиваем её сразу с этим разделом
    toggle()
    openSections.value = new Set([...openSections.value, section.key])
    return
  }
  const next = new Set(openSections.value)
  if (next.has(section.key)) next.delete(section.key)
  else next.add(section.key)
  openSections.value = next
}

function open(tab) {
  emit('open', tab)
  if (window.innerWidth < 900) expanded.value = false
}

// раздел подсвечен, если открыт он сам или любой его подпункт
function sectionIsActive(section) {
  return section.key === props.activeTab || section.items?.some((item) => item.key === props.activeTab)
}
</script>

<template>
  <nav :class="['sidebar', { expanded }]">
    <button class="toggle" :title="expanded ? 'Свернуть меню' : 'Развернуть меню'" @click="toggle">
      <span aria-hidden="true">☰</span>
      <span v-if="expanded" class="toggle-label">Меню</span>
    </button>

    <div v-for="section in sections" :key="section.key" class="section">
      <button
        :class="['section-button', { active: sectionIsActive(section) }]"
        :title="expanded ? '' : section.label"
        :aria-expanded="section.items ? openSections.has(section.key) : undefined"
        @click="section.items ? toggleSection(section) : open(section.key)"
      >
        <span class="icon" aria-hidden="true">{{ section.icon }}</span>
        <span v-if="expanded" class="label">{{ section.label }}</span>
        <span
          v-if="expanded && section.items"
          :class="['chevron', { open: openSections.has(section.key) }]"
          aria-hidden="true"
          >›</span
        >
      </button>

      <div v-if="expanded && section.items && openSections.has(section.key)" class="items">
        <button
          v-for="item in section.items"
          :key="item.key"
          :class="['item-button', { active: item.key === activeTab }]"
          @click="open(item.key)"
        >
          {{ item.label }}
        </button>
      </div>
    </div>

    <!-- внизу: кто вошёл и в каком офисе. Диспетчер офис не выбирает — он из учётки -->
    <div class="account">
      <template v-if="expanded">
        <div class="account-name" :title="user.login">{{ user.name }}</div>
        <select
          v-if="isAdmin"
          :value="officeId"
          class="office-select"
          aria-label="офис, с которым работаете"
          title="Офис, с которым работаете"
          @change="emit('choose-office', Number($event.target.value))"
        >
          <option v-for="office in offices" :key="office.id" :value="office.id">Офис «{{ office.name }}»</option>
        </select>
        <div v-else class="account-office">Офис «{{ officeName }}»</div>
      </template>
      <button
        class="logout"
        :title="expanded ? '' : `${user.name} · офис «${officeName}» · выйти`"
        @click="emit('logout')"
      >
        <span class="icon" aria-hidden="true">⎋</span>
        <span v-if="expanded" class="label">Выйти</span>
      </button>
    </div>
  </nav>
</template>

<style scoped>
.sidebar {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 52px;
  padding: 8px 6px;
  border-right: 1px solid #e2e8f0;
  background: #f8fafc;
  transition: width 0.15s ease;
  overflow: hidden;
}

.sidebar.expanded {
  width: 210px;
}

.sidebar button {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  border: none;
  border-radius: 6px;
  background: none;
  text-align: left;
  white-space: nowrap;
}

.toggle {
  margin-bottom: 6px;
  color: #64748b;
}

.toggle-label {
  font-size: 13px;
}

.section-button {
  padding: 8px 10px;
  font-weight: 600;
  color: #334155;
}

.section-button.active {
  background: #e0e7ff;
  color: #1d4ed8;
}

.chevron {
  margin-left: auto;
  color: #94a3b8;
  font-size: 16px;
  line-height: 1;
  transition: transform 0.15s ease;
}

.chevron.open {
  transform: rotate(90deg);
}

.icon {
  width: 18px;
  text-align: center;
  font-size: 15px;
}

.items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 2px 0 6px 28px;
}

.item-button {
  padding: 5px 10px;
  font-size: 13px;
  color: #475569;
}

.item-button.active {
  background: #eff6ff;
  color: #1d4ed8;
}

.account {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid #e2e8f0;
}

.account-name {
  padding: 0 10px;
  overflow: hidden;
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.account-office {
  padding: 0 10px;
  color: #64748b;
  font-size: 12px;
  white-space: nowrap;
}

.office-select {
  margin: 0 4px;
  font-size: 12px;
}

.logout {
  padding: 8px 10px;
  color: #64748b;
  font-size: 13px;
}

.sidebar button:hover:not(.active) {
  background: #eef2f7;
  color: #1d4ed8;
}
</style>
