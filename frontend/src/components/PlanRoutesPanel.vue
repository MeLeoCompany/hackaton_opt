<script setup>
// Маршруты исполнителей: кто, куда и во сколько едет (ТЗ 2.4.2), и неназначенные заявки
// с причинами. Характеристики плана (назначено, исполнителей, пробег) — в строке плана
// в списке планов, здесь их не повторяем.
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue'

import { moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { statusCode } from '../utils/requestStatuses.js'
import { brigadeNow, routeProgress } from '../utils/routeFact.js'
import { usePlanFocus } from '../composables/usePlanFocus.js'
import { formatDuration } from '../utils/duration.js'
import { routeColor } from '../utils/routeColors.js'

import DurationInput from './DurationInput.vue'
import PlanVisitDialog from './PlanVisitDialog.vue'

const props = defineProps({
  plan: { type: Object, required: true },
  references: { type: Object, required: true },
  selectedEngineerId: { type: Number, default: null },
  besideMap: { type: Boolean, default: false }, // рядом с картой: карточки вместо таблицы
  approved: { type: Boolean, default: false }, // план утверждён — статусы визитов можно менять
  focusedRequestId: { type: Number, default: null }, // заявка, к которой перешли из «Заявок»
  // режим демонстрации у действующего плана: маршруты можно отметить и привести к плану
  syncable: { type: Boolean, default: false },
  // отмеченные маршруты — по бригадам; кнопка синхронизации у страницы, рядом с «Пересчитать»
  syncSelected: { type: Array, default: () => [] },
})
const emit = defineEmits([
  'select-engineer',
  'visit-status-changed',
  'focus-request',
  'allow-departure',
  'update:syncSelected',
])

// своя копия выбора: несколько щелчков подряд успевают раньше, чем страница вернёт новый список
const chosen = ref([...props.syncSelected])
watch(
  () => props.syncSelected,
  (value) => {
    chosen.value = [...value]
  },
)

function isSyncSelected(engineerId) {
  return chosen.value.includes(engineerId)
}

function setChosen(value) {
  chosen.value = value
  emit('update:syncSelected', value)
}

function toggleSync(engineerId) {
  setChosen(
    isSyncSelected(engineerId) ? chosen.value.filter((id) => id !== engineerId) : [...chosen.value, engineerId],
  )
}

const allSelected = computed(
  () => props.plan.routes.length > 0 && props.plan.routes.every((route) => isSyncSelected(route.engineer_id)),
)

function toggleAll() {
  setChosen(allSelected.value ? [] : props.plan.routes.map((route) => route.engineer_id))
}

// из подсвеченного визита — обратно к заявке на вкладке «Заявки»
const { openRequest } = usePlanFocus()

// у визита показываем статус, только когда бригада до него уже добралась или его отменили:
// «В плане» у каждого визита утверждённого плана — шум
const MARKED_STATUSES = ['en_route', 'in_progress', 'done', 'cancelled']

// визит утверждённого плана, чья заявка за ним больше не закреплена: её вернули в «Новая»,
// и она ждёт нового расчёта — в этом плане бригада к ней не едет
function removedFromPlan(visit) {
  return props.approved && visit.approved_plan_id !== props.plan.id
}

// '' — без плашки; иначе код для класса плашки и её подпись
function visitMark(visit) {
  if (removedFromPlan(visit)) return 'removed'
  const code = statusCode(props.references, visit.status_id)
  return MARKED_STATUSES.includes(code) ? code : ''
}

// где бригада сейчас и сколько закрыла — только у утверждённого плана: по нему бригады ездят
function brigadeState(route) {
  if (!props.approved) return ''
  const { done, total } = routeProgress(route, props.references, props.plan.id)
  return `закрыто ${done} из ${total} · ${brigadeNow(route, props.references, props.plan.id).text}`
}

// отставание от плана по отметкам бригады: меньше 5 минут — не шум
const LATE_MINUTES = 5

function lateText(route) {
  if (!props.approved || (route.delay_minutes ?? 0) < LATE_MINUTES) return ''
  // маршрут закрыт — опаздывать уже некуда; иначе после перемотки времени висят «803 ч»
  const { done, total } = routeProgress(route, props.references, props.plan.id)
  if (total && done >= total) return ''
  const atRisk = route.at_risk_request_ids ?? []
  const risk = atRisk.length ? ` · не успевает к окну: ${atRisk.map((id) => `№${id}`).join(', ')}` : ''
  return `опаздывает на ${formatDuration(route.delay_minutes)}${risk}`
}

// бригада выбилась из плана: выезд закрыт, пока оператор не разрешит или не пересчитает
// (docs/algoV2.md, шаги 7-9)
function waitingText(route) {
  if (!props.approved || !route.waiting_reason) return ''
  return `ждёт плана · ${route.waiting_reason}`
}

function visitMarkName(visit) {
  if (removedFromPlan(visit)) return 'Снята с плана'
  return referenceName(props.references, 'request_statuses', visit.status_id)
}

function onVisitStatusChanged(statusId) {
  const { visit } = openedVisit.value
  emit('visit-status-changed', visit.request_id, statusId)
}

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

// клик по визиту: он подсвечивается (и на карте) и открывается окно «почему так»
function showVisit(route, visit) {
  emit('focus-request', visit.request_id)
  openedVisit.value = { route, visit }
}

// перешли из «Заявок» — прокручиваем к подсвеченной заявке, даже если бригад много
const panelRoot = ref(null)

async function scrollToFocused() {
  if (props.focusedRequestId === null) return
  await nextTick()
  panelRoot.value?.querySelector('.focused')?.scrollIntoView({ block: 'nearest' })
}

watch(() => [props.focusedRequestId, props.besideMap], scrollToFocused)
onMounted(scrollToFocused)

// открыли другой план — поиск от прошлого плана не переносим
watch(() => props.plan.id, () => {
  resetRouteFilters()
  openedVisit.value = null
})
</script>

<template>
  <section ref="panelRoot" class="routes-panel">

    <section class="plan-block">

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
            :class="['route-card', { selected: route.engineer_id === selectedEngineerId, 'with-sync': syncable }]"
            @click="emit('select-engineer', route.engineer_id)"
          >
            <!-- галочка — на своём поле слева: заголовок и строки под ним начинаются от одной линии -->
            <input
              v-if="syncable"
              type="checkbox"
              class="card-sync-check"
              :checked="isSyncSelected(route.engineer_id)"
              :aria-label="`синхронизировать маршрут ${route.engineer_name}`"
              @click.stop
              @change="toggleSync(route.engineer_id)"
            />
            <header>
              <i class="legend-dot" :style="{ background: routeColor(routeIndex) }"></i>
              <strong>{{ route.engineer_name }}</strong>
              <a v-if="route.phone" class="phone" :href="`tel:${route.phone}`" @click.stop>{{ route.phone }}</a>
              <span class="muted">{{ referenceName(references, 'transports', route.transport_id) }}</span>
            </header>
            <p v-if="brigadeState(route)" class="brigade-state">{{ brigadeState(route) }}</p>
            <p v-if="lateText(route)" class="brigade-late">{{ lateText(route) }}</p>
            <p v-if="waitingText(route)" class="brigade-waiting">
              {{ waitingText(route) }}
              <button
                title="Клиент согласился подождать: бригада едет как есть"
                @click.stop="emit('allow-departure', route.waiting_request_id)"
              >
                Разрешить выезд
              </button>
            </p>
            <p class="muted">
              {{ route.visits.length }} заявок · {{ route.distance_km.toFixed(1) }} км ·
              {{ formatDuration(route.duration_min) }} в пути
              <template v-if="route.provider !== 'valhalla'"> · оценка по прямой</template>
            </p>
            <ol class="visits">
              <li
                v-for="visit in route.visits"
                :key="visit.request_id"
                :class="['visit-main', { focused: visit.request_id === focusedRequestId }]"
                title="Почему визит стоит здесь"
                @click.stop="showVisit(route, visit)"
              >
                <span class="time">{{ moscowTimeOf(visit.planned_arrival_time) }}</span>
                <span :class="['visit-address', { 'visit-closed': ['done', 'cancelled', 'removed'].includes(visitMark(visit)), 'visit-removed': visitMark(visit) === 'removed' }]">
                  №{{ visit.request_id }} · {{ visit.address }}
                </span>
                <span v-if="visitMark(visit)" :class="['status-badge', `status-${visitMark(visit)}`]">
                  {{ visitMarkName(visit) }}
                </span>
                <button
                  type="button"
                  :class="['back-to-request', { shown: visit.request_id === focusedRequestId }]"
                  :tabindex="visit.request_id === focusedRequestId ? 0 : -1"
                  :aria-hidden="visit.request_id !== focusedRequestId"
                  title="К этой заявке на вкладке «Заявки»"
                  aria-label="К этой заявке на вкладке «Заявки»"
                  @click.stop="openRequest(visit.request_id)"
                >
                  ↩
                </button>
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
            <col v-if="syncable" style="width: 36px" />
            <col style="width: 220px" />
            <!-- «Общественный транспорт» — самое длинное название, помещается в одну строку -->
            <col style="width: 190px" />
            <col style="width: 110px" />
            <col style="width: 110px" />
            <col style="width: 180px" />
            <col />
          </colgroup>
          <thead>
            <tr>
              <!-- галочки синхронизации с планом (режим демонстрации): «все» — здесь -->
              <th v-if="syncable" class="sync-cell">
                <input
                  type="checkbox"
                  :checked="allSelected"
                  title="Выбрать все маршруты"
                  aria-label="выбрать все маршруты"
                  @change="toggleAll"
                />
              </th>
              <th>Бригада</th>
              <th>Транспорт</th>
              <th>Заявок</th>
              <th>Пробег, км</th>
              <th>В пути</th>
              <th>Маршрут</th>
            </tr>
            <tr class="filter-row filter-controls">
              <th v-if="syncable"></th>
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
              <td :colspan="syncable ? 7 : 6" class="muted">Ни один маршрут не подходит под фильтры</td>
            </tr>
            <tr
              v-for="{ route, routeIndex } in visibleRoutes"
              :key="route.engineer_id"
              :class="{ selected: route.engineer_id === selectedEngineerId }"
              @click="emit('select-engineer', route.engineer_id)"
            >
              <td v-if="syncable" class="sync-cell" @click.stop>
                <input
                  type="checkbox"
                  :checked="isSyncSelected(route.engineer_id)"
                  :aria-label="`синхронизировать маршрут ${route.engineer_name}`"
                  @change="toggleSync(route.engineer_id)"
                />
              </td>
              <td>
                <i class="legend-dot" :style="{ background: routeColor(routeIndex) }"></i>
                <strong>{{ route.engineer_name }}</strong>
                <a v-if="route.phone" class="phone" :href="`tel:${route.phone}`" @click.stop>{{ route.phone }}</a>
                <span v-if="brigadeState(route)" class="brigade-state">{{ brigadeState(route) }}</span>
                <span v-if="lateText(route)" class="brigade-late">{{ lateText(route) }}</span>
                <span v-if="waitingText(route)" class="brigade-waiting">
                  {{ waitingText(route) }}
                  <button
                    title="Клиент согласился подождать: бригада едет как есть"
                    @click.stop="emit('allow-departure', route.waiting_request_id)"
                  >
                    Разрешить выезд
                  </button>
                </span>
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
                    :class="['visit-step', { focused: visit.request_id === focusedRequestId }]"
                    title="Почему визит стоит здесь"
                    @click.stop="showVisit(route, visit)"
                  >
                    <span class="route-arrow" aria-hidden="true">↓</span>
                    <span class="time">{{ moscowTimeOf(visit.planned_arrival_time) }}</span>
                    <span :class="['visit-address', { 'visit-closed': ['done', 'cancelled', 'removed'].includes(visitMark(visit)), 'visit-removed': visitMark(visit) === 'removed' }]">
                      №{{ visit.request_id }} · {{ visit.address }}
                    </span>
                    <span v-if="visitMark(visit)" :class="['status-badge', `status-${visitMark(visit)}`]">
                      {{ visitMarkName(visit) }}
                    </span>
                    <button
                      type="button"
                      :class="['back-to-request', { shown: visit.request_id === focusedRequestId }]"
                      :tabindex="visit.request_id === focusedRequestId ? 0 : -1"
                      :aria-hidden="visit.request_id !== focusedRequestId"
                      title="К этой заявке на вкладке «Заявки»"
                      aria-label="К этой заявке на вкладке «Заявки»"
                      @click.stop="openRequest(visit.request_id)"
                    >
                      ↩
                    </button>
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
          <!-- 110 + 680 = 790 — там же, где начинается «Маршрут» в таблице выше:
               линия колонки идёт через обе таблицы -->
          <colgroup v-if="!besideMap">
            <col style="width: 110px" />
            <col style="width: 680px" />
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
      :approved="approved"
      :plan-id="plan.id"
      @close="openedVisit = null"
      @status-changed="onVisitStatusChanged"
    />
  </section>
</template>

<style scoped>
/* галочки синхронизации с планом — своя колонка, по центру. Отступы у заголовка и строк
   разные (10 и 13 пикселей), а колонка узкая — без них галочки встают строго друг под другом */
.data-table.routes-table th.sync-cell,
.data-table.routes-table td.sync-cell {
  padding-right: 0;
  padding-left: 0;
  text-align: center;
}

.sync-cell input {
  width: 15px;
  height: 15px;
  margin: 0;
  padding: 0;
  vertical-align: middle;
}

.routes-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 13px;
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

/* поиск отдельной строкой под заголовком — во всю ширину панели, вровень с карточками */
.route-search {
  width: 100%;
}

/* карточки маршрутов рядом с картой: в узкой колонке встают в один столбец */
.route-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 8px;
  align-items: start;
}

.route-card {
  position: relative;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  cursor: pointer;
}

/* режим демонстрации: слева поле под галочку, всё содержимое карточки — правее него */
.route-card.with-sync {
  padding-left: 36px;
}

/* по высоте — напротив первой строки названия: у заголовка строка 20 пикселей, сверху отступ
   карточки 10 — центр строки на 20, галочка 15 — её верх на 12.5 */
.card-sync-check {
  position: absolute;
  top: 12.5px;
  left: 12px;
  width: 15px;
  height: 15px;
  margin: 0;
  padding: 0;
}

.route-card:hover {
  border-color: #93c5fd;
}

.route-card.selected {
  border-color: #2563eb;
  background: #eff6ff;
}

/* название бригады бывает в две строки — всё в шапке держится первой строки, как и галочка */
.route-card header {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  line-height: 20px;
}

.route-card header .legend-dot {
  flex: none;
  margin-top: 5px;
}

.route-card p {
  margin: 4px 0 6px;
}

/* бригада отстаёт от плана — красным: к части заявок может не успеть */
.brigade-late {
  display: block;
  margin: 2px 0 0;
  color: #b91c1c;
  font-size: 12px;
  font-weight: 600;
}

/* бригада ждёт нового плана: выезд закрыт, пока оператор не разрешит или не пересчитает */
.brigade-waiting {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin: 4px 0 0;
  color: #92400e;
  font-size: 12px;
  font-weight: 600;
}

.brigade-waiting button {
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 400;
}

/* телефон бригады: оператор звонит прямо из плана */
.phone {
  margin-left: 6px;
  color: #1d4ed8;
  font-size: 12px;
  white-space: nowrap;
}

/* где бригада сейчас — по её отметкам в мобильном приложении */
.brigade-state {
  display: block;
  margin: 2px 0 0;
  color: #b45309;
  font-size: 12px;
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

/* заявка, к которой перешли из «Заявок», — подсвечена так же, как выбранная строка таблицы */
.visit-step.focused,
.visits li.focused {
  background: #fef9c3;
}

/* мини-стрелка «обратно к заявке»: место под неё справа есть в каждом визите, поэтому она
   не прыгает вслед за длиной адреса; видна только у подсвеченного визита */
.back-to-request {
  flex-shrink: 0;
  align-self: center;
  width: 22px;
  min-width: 0;
  height: 20px;
  padding: 0;
  border: 1px solid #fde68a;
  border-radius: 6px;
  background: #fff;
  color: #1d4ed8;
  font-size: 13px;
  line-height: 18px;
  cursor: pointer;
  visibility: hidden;
}

/* стрелка загорается у подсвеченного визита и у визита под курсором — к любой заявке
   маршрута можно перейти, не выбирая её сначала */
.back-to-request.shown,
.visit-step:hover .back-to-request,
.visits li:hover .back-to-request {
  visibility: visible;
}

.back-to-request:hover:not(:disabled) {
  border-color: #2563eb;
  background: #2563eb;
  color: #fff;
}

.visit-address {
  flex: 1;
  min-width: 0;
}

/* визит закрыт — выполнен или отменён: бригаде туда больше не надо */
.visit-closed {
  color: #94a3b8;
}

/* заявку сняли с плана — зачёркнута: в этом маршруте её больше нет */
.visit-removed {
  text-decoration: line-through;
}

.status-badge.status-removed {
  background: #f1f5f9;
  color: #64748b;
  border: 1px dashed #cbd5e1;
}

.visit-step .status-badge,
.visits .status-badge {
  flex-shrink: 0;
  margin-left: 6px;
  padding: 0 6px;
  font-size: 11px;
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

/* визит в таблице — строкой: адрес растягивается, стрелка «к заявке» — у правого края */
.route-steps li.visit-step {
  display: flex;
  align-items: baseline;
  gap: 6px;
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
