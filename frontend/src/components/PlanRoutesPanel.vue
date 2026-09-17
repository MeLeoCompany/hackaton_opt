<script setup>
// Маршруты исполнителей: кто, куда и во сколько едет (ТЗ 2.4.2), и неназначенные заявки
// с причинами. Характеристики плана (назначено, исполнителей, пробег) — в строке плана
// в списке планов, здесь их не повторяем.
import { computed, reactive, ref, watch } from 'vue'

import { formatDay, moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { formatDuration } from '../utils/duration.js'
import { routeColor } from '../utils/routeColors.js'

import DurationInput from './DurationInput.vue'
import PlanVisitDialog from './PlanVisitDialog.vue'

const props = defineProps({
  plan: { type: Object, required: true },
  references: { type: Object, required: true },
  selectedEngineerId: { type: Number, default: null },
  besideMap: { type: Boolean, default: false }, // рядом с картой: карточки вместо таблицы
})
const emit = defineEmits(['select-engineer'])

// Поиск маршрутов. В таблице — по колонкам в её шапке, как в заявках и исполнителях;
// в карточках рядом с картой шапки нет, там одно общее поле.
const EMPTY_ROUTE_FILTERS = {
  name: '', // часть названия бригады
  transportId: '', // '' — любой транспорт
  visitsFrom: '', // заявок в маршруте не меньше
  visitsTo: '', // и не больше
  distanceFrom: '', // пробег, км, не меньше
  distanceTo: '', // и не больше
  durationFrom: '', // в пути, минут не меньше
  durationTo: '', // и не больше
  visit: '', // номер или часть адреса заявки в маршруте
}
const routeFilters = reactive({ ...EMPTY_ROUTE_FILTERS })
const routeQuery = ref('')

function visitsMatch(route, query) {
  return route.visits.some(
    (visit) => String(visit.request_id).includes(query) || visit.address.toLowerCase().includes(query),
  )
}

function inRange(value, from, to) {
  return (from === '' || value >= Number(from)) && (to === '' || value <= Number(to))
}

// номер маршрута в плане хранится вместе с маршрутом: по нему выбирается цвет,
// и после поиска у бригады остаётся тот же цвет, что на карте
const visibleRoutes = computed(() => {
  const name = routeFilters.name.trim().toLowerCase()
  const visit = routeFilters.visit.trim().toLowerCase()
  const query = routeQuery.value.trim().toLowerCase()

  return props.plan.routes
    .map((route, routeIndex) => ({ route, routeIndex }))
    .filter(({ route }) => !name || route.engineer_name.toLowerCase().includes(name))
    .filter(({ route }) => routeFilters.transportId === '' || route.transport_id === routeFilters.transportId)
    .filter(({ route }) => inRange(route.visits.length, routeFilters.visitsFrom, routeFilters.visitsTo))
    .filter(({ route }) => inRange(route.distance_km, routeFilters.distanceFrom, routeFilters.distanceTo))
    .filter(({ route }) => inRange(Math.round(route.duration_min), routeFilters.durationFrom, routeFilters.durationTo))
    .filter(({ route }) => !visit || visitsMatch(route, visit))
    .filter(({ route }) => !query || route.engineer_name.toLowerCase().includes(query) || visitsMatch(route, query))
})

const activeRouteFilterCount = computed(
  () => Object.keys(EMPTY_ROUTE_FILTERS).filter((name) => routeFilters[name] !== EMPTY_ROUTE_FILTERS[name]).length,
)

function resetRouteFilters() {
  Object.assign(routeFilters, EMPTY_ROUTE_FILTERS)
  routeQuery.value = ''
}

// визит, открытый в окне «почему так»: { visit, route }
const openedVisit = ref(null)

function showVisit(route, visit) {
  openedVisit.value = { route, visit }
}

// открыли другой план — поиск от прошлого плана не переносим
watch(() => props.plan.id, () => {
  resetRouteFilters()
  openedVisit.value = null
})
</script>

<template>
  <section class="routes-panel">
    <header v-if="!besideMap" class="plan-title">
      <h2>План №{{ plan.id }} на {{ formatDay(plan.plan_date) }}</h2>
    </header>


    <section class="plan-block">
      <h3>Маршруты исполнителей</h3>

      <!-- рядом с картой места мало: маршруты карточками и одно поле поиска -->
      <template v-if="besideMap">
        <div class="filter-controls route-search">
          <input v-model="routeQuery" placeholder="Поиск: бригада, № заявки или адрес" aria-label="поиск маршрута" />
        </div>
        <p v-if="!visibleRoutes.length" class="muted">Ни один маршрут не подходит под поиск</p>
        <div class="route-cards">
          <article
            v-for="{ route, routeIndex } in visibleRoutes"
            :key="route.engineer_id"
            :class="['route-card', { selected: route.engineer_id === selectedEngineerId }]"
            @click="emit('select-engineer', route.engineer_id)"
          >
            <header>
              <i class="legend-dot" :style="{ background: routeColor(routeIndex) }"></i>
              <strong>{{ route.engineer_name }}</strong>
              <span class="muted">{{ referenceName(references, 'transports', route.transport_id) }}</span>
            </header>
            <p class="muted">
              {{ route.visits.length }} заявок · {{ route.distance_km.toFixed(1) }} км ·
              {{ formatDuration(route.duration_min) }} в пути
              <template v-if="route.provider !== 'valhalla'"> · оценка по прямой</template>
            </p>
            <ol class="visits">
              <li
                v-for="visit in route.visits"
                :key="visit.request_id"
                class="visit-main"
                title="Почему визит стоит здесь"
                @click.stop="showVisit(route, visit)"
              >
                <span class="time">{{ moscowTimeOf(visit.planned_arrival_time) }}</span>
                <span>№{{ visit.request_id }} · {{ visit.address }}</span>
              </li>
            </ol>
          </article>
        </div>
      </template>

      <!-- в характеристиках — таблицей, поиск по колонкам в её шапке -->
      <div v-else class="table-scroll">
        <!-- ширины колонок фиксированы: иначе таблица разъезжается при каждом вводе в фильтр;
             узкие колонки с числами, всё остальное место — маршруту с адресами -->
        <table class="data-table fixed-columns routes-table">
          <colgroup>
            <col style="width: 220px" />
            <col style="width: 170px" />
            <col style="width: 110px" />
            <col style="width: 110px" />
            <col style="width: 180px" />
            <col />
          </colgroup>
          <thead>
            <tr>
              <th>Бригада</th>
              <th>Транспорт</th>
              <th>Заявок</th>
              <th>Пробег, км</th>
              <th>В пути</th>
              <th>Маршрут</th>
            </tr>
            <tr class="filter-row filter-controls">
              <th><input v-model="routeFilters.name" placeholder="бригада" aria-label="поиск по бригаде" /></th>
              <th>
                <select v-model="routeFilters.transportId" aria-label="фильтр по транспорту">
                  <option value="">любой</option>
                  <option v-for="item in references.transports" :key="item.id" :value="item.id">{{ item.name }}</option>
                </select>
              </th>
              <th>
                <div class="range-pair">
                  <input v-model="routeFilters.visitsFrom" type="number" min="0" placeholder="от" aria-label="заявок не меньше" />
                  <span>–</span>
                  <input v-model="routeFilters.visitsTo" type="number" min="0" placeholder="до" aria-label="заявок не больше" />
                </div>
              </th>
              <th>
                <div class="range-pair">
                  <input v-model="routeFilters.distanceFrom" type="number" min="0" placeholder="от" aria-label="пробег не меньше, км" />
                  <span>–</span>
                  <input v-model="routeFilters.distanceTo" type="number" min="0" placeholder="до" aria-label="пробег не больше, км" />
                </div>
              </th>
              <th>
                <div class="range-pair">
                  <DurationInput v-model="routeFilters.durationFrom" placeholder="от" aria-label="в пути не меньше" />
                  <span>–</span>
                  <DurationInput v-model="routeFilters.durationTo" placeholder="до" aria-label="в пути не больше" />
                </div>
              </th>
              <th>
                <!-- у маршрутов нет колонки с кнопками, поэтому сброс стоит рядом с последним фильтром -->
                <div class="filter-with-reset">
                  <input v-model="routeFilters.visit" placeholder="№ или адрес заявки" aria-label="поиск по заявкам маршрута" />
                  <button class="link" :disabled="activeRouteFilterCount === 0" @click="resetRouteFilters">
                    Сбросить{{ activeRouteFilterCount ? ` (${activeRouteFilterCount})` : '' }}
                  </button>
                </div>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!visibleRoutes.length">
              <td colspan="6" class="muted">Ни один маршрут не подходит под фильтры</td>
            </tr>
            <tr
              v-for="{ route, routeIndex } in visibleRoutes"
              :key="route.engineer_id"
              :class="{ selected: route.engineer_id === selectedEngineerId }"
              @click="emit('select-engineer', route.engineer_id)"
            >
              <td class="nowrap">
                <i class="legend-dot" :style="{ background: routeColor(routeIndex) }"></i>
                <strong>{{ route.engineer_name }}</strong>
              </td>
              <td class="nowrap">{{ referenceName(references, 'transports', route.transport_id) }}</td>
              <td class="under-range-filter">{{ route.visits.length }}</td>
              <td
                class="under-range-filter"
                :title="route.provider !== 'valhalla' ? 'Оценка по прямой: маршрутизатор был недоступен' : ''"
              >
                {{ route.distance_km.toFixed(1) }}<template v-if="route.provider !== 'valhalla'">*</template>
              </td>
              <td class="under-range-filter nowrap">{{ formatDuration(route.duration_min) }}</td>
              <td>
                <!-- маршрут сверху вниз: старт бригады, затем заявки по порядку, между ними стрелки -->
                <ol class="route-steps">
                  <li class="route-start">Старт</li>
                  <li
                    v-for="visit in route.visits"
                    :key="visit.request_id"
                    class="visit-step"
                    title="Почему визит стоит здесь"
                    @click.stop="showVisit(route, visit)"
                  >
                    <span class="route-arrow" aria-hidden="true">↓</span>
                    <span class="time">{{ moscowTimeOf(visit.planned_arrival_time) }}</span>
                    <span>№{{ visit.request_id }} · {{ visit.address }}</span>
                  </li>
                </ol>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="plan.unassigned.length" class="plan-block">
      <h3>Не назначены в этом плане</h3>
      <div class="table-scroll">
        <!-- рядом с картой панель узкая — там ширины подбираются сами -->
        <table :class="['data-table', { 'fixed-columns': !besideMap }]">
          <colgroup v-if="!besideMap">
            <col style="width: 110px" />
            <col style="width: 45%" />
            <col />
          </colgroup>
          <thead>
            <tr>
              <th>№</th>
              <th>Адрес</th>
              <th v-if="!besideMap">Причина</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="request in plan.unassigned" :key="request.request_id" :title="request.reason">
              <td class="nowrap">{{ request.request_id }}</td>
              <td>{{ request.address }}</td>
              <td v-if="!besideMap" class="muted">{{ request.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
    <PlanVisitDialog
      v-if="openedVisit"
      :visit="openedVisit.visit"
      :route="openedVisit.route"
      :references="references"
      @close="openedVisit = null"
    />
  </section>
</template>

<style scoped>
.routes-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 13px;
}

.plan-title h2 {
  margin: 0;
  font-size: 16px;
}

.plan-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* у абзацев-пояснений браузерные отступы складываются с gap — получается дыра в строку */
.plan-block > p {
  margin: 0;
}

.plan-block h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* поиск отдельной строкой под заголовком: подсказка помещается целиком */
.route-search {
  width: 340px;
  max-width: 100%;
}

/* карточки маршрутов рядом с картой: в узкой колонке встают в один столбец */
.route-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px;
  align-items: start;
}

.route-card {
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: pointer;
}

.route-card:hover {
  border-color: #93c5fd;
}

.route-card.selected {
  border-color: #2563eb;
  background: #eff6ff;
}

.route-card header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.route-card p {
  margin: 4px 0 6px;
}

/* маршруты — строками, как остальные таблицы; клик по строке показывает маршрут на карте */
.routes-table tbody tr {
  cursor: pointer;
}

.routes-table td.under-range-filter {
  font-variant-numeric: tabular-nums;
}

.routes-table .legend-dot {
  margin-right: 6px;
}

.visits {
  margin: 0;
  padding-left: 18px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.visit-main {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

/* визит кликается: по нему открывается окно «почему так» */
.visit-step,
.visits li {
  cursor: pointer;
  border-radius: 4px;
}

.visit-step:hover,
.visits li:hover {
  background: #eff6ff;
  color: #1d4ed8;
}

.filter-with-reset {
  display: flex;
  align-items: center;
  gap: 10px;
}

.filter-with-reset input {
  flex: 1;
}

/* шаги маршрута столбиком: «Старт», дальше каждая заявка со стрелкой перехода слева */
.route-steps {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.route-steps li {
  display: block;
}

.route-start {
  color: #64748b;
  font-size: 12px;
}

.route-arrow {
  width: 12px;
  color: #94a3b8;
  text-align: center;
}

.time {
  display: inline-block;
  min-width: 42px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
