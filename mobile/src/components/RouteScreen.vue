<script setup>
// Маршрут бригады на день: шапка с днём и прогрессом, текущая заявка с кнопками сверху,
// ниже — весь маршрут по порядку. Маршрут обновляется сам раз в минуту: диспетчер мог
// пересчитать план.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

import { currentVisit, formatDay, isClosed, moscowTime, progress } from '../route.js'
import { useBrigade } from '../useBrigade.js'
import FailSheet from './FailSheet.vue'
import VisitCard from './VisitCard.vue'

const { user, days, day, route, loading, busy, errorMessage, logout, loadRoute, selectDay, mark } = useBrigade()

const current = computed(() => currentVisit(route.value))
const counts = computed(() => progress(route.value))
// что ещё впереди после текущей и что уже закрыто — отдельными списками
const upcoming = computed(
  () => route.value?.visits.filter((visit) => visit !== current.value && !isClosed(visit)) ?? [],
)
const closedVisits = computed(() => route.value?.visits.filter(isClosed) ?? [])
const failing = ref(null) // заявка, для которой открыт выбор причины

async function confirmFail(reason) {
  const visit = failing.value
  failing.value = null
  await mark(visit, 'fail', reason)
}

const REFRESH_MS = 60_000
let timer = null
onMounted(() => {
  timer = setInterval(() => {
    if (!busy.value && !failing.value) loadRoute()
  }, REFRESH_MS)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="screen">
    <header class="top">
      <div class="who">
        <strong>{{ user.brigade_name }}</strong>
        <span>{{ user.office_name }}</span>
      </div>
      <button class="ghost light" @click="logout">Выйти</button>
    </header>

    <div class="day-bar">
      <select
        v-if="days.length"
        :value="day"
        aria-label="день маршрута"
        @change="selectDay($event.target.value)"
      >
        <option v-for="item in days" :key="item" :value="item">{{ formatDay(item) }}</option>
      </select>
      <span v-if="route?.shift_start" class="shift">
        смена {{ moscowTime(route.shift_start) }}–{{ moscowTime(route.shift_end) }}
      </span>
      <button class="ghost light refresh" :disabled="loading" aria-label="обновить" @click="loadRoute">⟳</button>
    </div>

    <div v-if="counts.total" class="progress">
      <div class="progress-bar">
        <span :style="{ width: `${(counts.done / counts.total) * 100}%` }"></span>
      </div>
      <span>Закрыто {{ counts.done }} из {{ counts.total }}</span>
    </div>

    <main>
      <p v-if="errorMessage" class="error" role="alert">
        {{ errorMessage }}
        <button class="close" aria-label="закрыть" @click="errorMessage = ''">×</button>
      </p>

      <p v-if="!days.length" class="empty">
        Маршрутов пока нет: диспетчер ещё не утвердил план с вашей бригадой.
      </p>
      <p v-else-if="loading && !route" class="empty">Загружаю маршрут…</p>
      <p v-else-if="route && !route.visits.length" class="empty">На этот день в плане заявок нет.</p>

      <template v-else-if="route">
        <section v-if="current" class="block">
          <h2>Сейчас</h2>
          <VisitCard :visit="current" current :busy="busy" @mark="mark" @fail="failing = $event" />
        </section>
        <p v-else class="empty done">Все заявки маршрута закрыты. Хорошая работа!</p>

        <section v-if="upcoming.length" class="block">
          <h2>Дальше по маршруту · {{ upcoming.length }}</h2>
          <VisitCard v-for="visit in upcoming" :key="visit.request_id" :visit="visit" />
        </section>

        <section v-if="closedVisits.length" class="block">
          <h2>Закрытые · {{ closedVisits.length }}</h2>
          <VisitCard v-for="visit in closedVisits" :key="visit.request_id" :visit="visit" />
        </section>
      </template>
    </main>

    <FailSheet v-if="failing" :visit="failing" :busy="busy" @confirm="confirmFail" @close="failing = null" />
  </div>
</template>

<style scoped>
.screen {
  display: flex;
  flex-direction: column;
  min-height: 100%;
  background: #f3f4f6;
}

.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 16px 10px;
  background: #111827;
  color: #fff;
}

.who {
  display: flex;
  flex-direction: column;
}

.who strong {
  font-size: 18px;
}

.who span {
  color: #9ca3af;
  font-size: 13px;
}

.day-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px 12px;
  background: #111827;
  color: #d1d5db;
  font-size: 13px;
}

.day-bar select {
  padding: 6px 10px;
  border: 0;
  border-radius: 10px;
  background: #1f2937;
  color: #fff;
  font: inherit;
  font-weight: 600;
}

.refresh {
  margin-left: auto;
  font-size: 16px;
}

.progress {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: #fff;
  color: #4b5563;
  font-size: 13px;
  border-bottom: 1px solid #e5e7eb;
}

.progress-bar {
  flex: 1;
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: #e5e7eb;
}

.progress-bar span {
  display: block;
  height: 100%;
  background: #16a34a;
  transition: width 0.3s;
}

main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 14px 12px 24px;
}

.block {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

h2 {
  margin: 0 4px;
  color: #6b7280;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.empty {
  margin: 20px 8px;
  color: #6b7280;
  font-size: 15px;
  text-align: center;
}

.empty.done {
  color: #15803d;
  font-weight: 600;
}

.error {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin: 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: #fef2f2;
  color: #991b1b;
  font-size: 14px;
}

.error .close {
  padding: 0 4px;
  border: 0;
  background: none;
  color: inherit;
  font-size: 18px;
  line-height: 1;
}
</style>
