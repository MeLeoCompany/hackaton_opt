<script setup>
// Параметры системы: к чему подключён бэкенд, что сейчас настроено и сколько чего заведено.
// Только для администратора; данные приходят одним запросом и обновляются по кнопке.
import { computed, onMounted, ref } from 'vue'

import ErrorMessage from '../components/ErrorMessage.vue'
import { clearTravelCache, fetchSolverParams, fetchTravelCache, saveSolverParams } from '../api/systemApi.js'
import InfoHint from '../components/InfoHint.vue'
import SolverParamRows from '../components/SolverParamRows.vue'
import { limitFor, numericParams } from '../utils/solverParams.js'
import { useSystemInfo } from '../composables/useSystemInfo.js'
import { useSystemTime } from '../composables/useSystemTime.js'
import { formatDay, moscowDateOf, moscowTimeOf } from '../utils/moscowTime.js'

const { info, loading, errorMessage, errorDetails, load } = useSystemInfo()

// параметры расчёта по умолчанию: их подставляет диалог расчёта, менять может администратор
const savedSolver = ref(null)
const savingSolver = ref(false)
const solverNotice = ref('')
// раскрытые группы настроек: cuOpt и службы вроде R5
const openGroups = ref(new Set())

function toggleGroup(key) {
  const next = new Set(openGroups.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  openGroups.value = next
}

// как группа называется в таблице: префикс в названии настройки — это служба
const GROUP_TITLES = { R5: 'Общественный транспорт R5' }

// настройки окружения: «R5: таймаут запроса, с» уходит в группу R5, остальное — отдельными строками
const settingGroups = computed(() => {
  const groups = new Map()
  const plain = []
  for (const [name, value] of Object.entries(info.value?.settings ?? {})) {
    const match = name.match(/^([^:]+):\s*(.+)$/)
    if (!match) {
      plain.push({ name, value })
      continue
    }
    if (!groups.has(match[1])) groups.set(match[1], [])
    // «таймаут запроса, с» -> «Таймаут запроса, с»: внутри группы префикса службы уже нет
    groups.get(match[1]).push({ name: match[2][0].toUpperCase() + match[2].slice(1), value })
  }
  return {
    groups: [...groups].map(([key, rows]) => ({
      key,
      title: GROUP_TITLES[key] ?? key,
      rows,
      // значения служб длинные (пути, адреса) — в свёрнутой группе хватит их числа
      summary: rows.length === 1 ? '1 параметр' : `${rows.length} ${rows.length < 5 ? 'параметра' : 'параметров'}`,
    })),
    plain,
  }
})

async function loadSolver() {
  try {
    savedSolver.value = await fetchSolverParams()
  } catch (error) {
    errorMessage.value = error.message
  }
}

// свёрнутая группа говорит главное: сколько ищем и с чем
const solverSummary = computed(() => {
  const params = savedSolver.value
  return (
    `поиск ${params.time_limit_seconds}–${params.max_time_limit_seconds} с ` +
    `(день из 200 точек — ${limitFor(params, 200)} с), вес пробега ${params.distance_weight}, ` +
    `попыток по расписанию ${params.transit_attempts}, лог ${params.verbose_log ? 'подробный' : 'обычный'}`
  )
})

// правка одной строки: сохраняем весь набор с новым значением — сервер проверит сочетание
async function saveOne(key, value) {
  savingSolver.value = true
  solverNotice.value = ''
  try {
    const next = numericParams({ ...savedSolver.value, [key]: value })
    savedSolver.value = await saveSolverParams(next)
    solverNotice.value = 'Сохранено: следующие расчёты пойдут с новыми параметрами'
  } catch (error) {
    errorMessage.value = [error.message, ...(error.details ?? [])].join(': ')
  } finally {
    savingSolver.value = false
  }
}

// кеш ответов R5: матрица и плечи маршрутов не считаются заново (docs/algoCachV1.md)
const travelCache = ref(null)
const clearingCache = ref(false)

async function loadTravelCache() {
  try {
    travelCache.value = await fetchTravelCache()
  } catch {
    // нет данных — строка кеша просто не покажется
  }
}

const travelCacheSummary = computed(() => {
  const cache = travelCache.value
  if (!cache.matrix_pairs && !cache.routes) return `пусто · хранится ${cache.keep_days} дней`
  const oldest = cache.oldest_at ? ` · самая старая запись ${moment(cache.oldest_at)}` : ''
  return (
    `пар матрицы ${cache.matrix_pairs.toLocaleString('ru-RU')}, плеч маршрутов ` +
    `${cache.routes.toLocaleString('ru-RU')} · хранится ${cache.keep_days} дней${oldest}`
  )
})

async function resetTravelCache() {
  if (!window.confirm('Сбросить кеш маршрутов R5? Следующие расчёты заново спросят R5 — первый будет дольше.')) return
  clearingCache.value = true
  try {
    const { deleted } = await clearTravelCache()
    solverNotice.value = `Кеш маршрутов сброшен: удалено записей ${deleted.toLocaleString('ru-RU')}`
    await loadTravelCache()
  } catch (error) {
    errorMessage.value = error.message
  } finally {
    clearingCache.value = false
  }
}

const { now, shifted, demoMode, setDemoMode } = useSystemTime()
const switchingDemo = ref(false)

// выключение возвращает часы к настоящему времени — предупреждаем, если они перемотаны
async function toggleDemo(enabled) {
  if (!enabled && shifted.value && !window.confirm('Выключить режим демонстрации? Часы вернутся к настоящему времени.')) {
    return
  }
  switchingDemo.value = true
  if (await setDemoMode(enabled)) await load()
  switchingDemo.value = false
}

function moment(isoString) {
  return isoString ? `${formatDay(moscowDateOf(isoString))} ${moscowTimeOf(isoString)}` : '—'
}

const clock = computed(() => moment(now.value.toISOString()))
const realClock = computed(() => moment(info.value?.time.real_now))

onMounted(() => {
  load()
  loadSolver()
  loadTravelCache()
})
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Система</h1>
      <p>Подключения, настройки и объёмы данных · время московское</p>
    </header>

    <ErrorMessage v-if="errorMessage" :message="errorMessage" :details="errorDetails" @close="errorMessage = ''" />

    <p v-if="loading && !info" class="muted">Загружаю параметры…</p>

    <template v-else-if="info">
      <section class="cards">
        <article class="card">
          <h2>Приложение</h2>
          <dl>
            <div><dt>Название</dt><dd>{{ info.app_name }}</dd></div>
            <div><dt>Версия</dt><dd>{{ info.version }}</dd></div>
            <div><dt>Python</dt><dd>{{ info.python_version }}</dd></div>
          </dl>
        </article>

        <article :class="['card', { warn: shifted }]">
          <div class="card-head">
            <h2>Системное время</h2>
            <!-- режим демонстрации: разрешает переводить часы и синхронизировать маршруты с планом -->
            <label class="demo-switch" title="Разрешает переводить время и синхронизировать маршруты с планом">
              <span>Режим демонстрации</span>
              <span class="switch">
                <input
                  type="checkbox"
                  :checked="demoMode"
                  :disabled="switchingDemo"
                  aria-label="режим демонстрации"
                  @change="toggleDemo($event.target.checked)"
                />
                <span class="slider"></span>
              </span>
            </label>
          </div>
          <dl>
            <div><dt>Сейчас в системе</dt><dd>{{ clock }}</dd></div>
            <div><dt>Настоящее время</dt><dd>{{ realClock }}</dd></div>
            <div v-if="shifted"><dt>Перемотал</dt><dd>{{ info.time.updated_by ?? '—' }}</dd></div>
          </dl>
          <p class="note">
            <template v-if="shifted">Время перемотано для демонстрации — часы вверху жёлтые.</template>
            <template v-else-if="demoMode">Время настоящее. Перемотать можно кликом по часам в правом верхнем углу.</template>
            <template v-else>
              Время настоящее. Переводить его и синхронизировать маршруты с планом можно в режиме
              демонстрации.
            </template>
          </p>
        </article>
      </section>

      <h2 class="section-title">Подключения</h2>
      <div class="table-scroll">
        <table class="data-table fixed-columns">
          <!-- первая колонка той же ширины, что у «Настроек расчёта»: колонки значений на одной вертикали -->
          <colgroup>
            <col style="width: 280px" />
            <col />
            <col style="width: 320px" />
          </colgroup>
          <thead>
            <tr><th>Служба</th><th>Адрес</th><th>Состояние</th></tr>
          </thead>
          <tbody>
            <tr v-for="service in info.services" :key="service.name">
              <td>{{ service.name }}</td>
              <td class="target">{{ service.target }}</td>
              <td>
                <span :class="['badge', service.ok ? 'ok' : 'fail']">{{ service.ok ? 'работает' : 'не отвечает' }}</span>
                <span class="detail">{{ service.detail }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2 class="section-title">Настройки расчёта</h2>
      <div class="table-scroll">
        <!-- параметры решателя — группой, как шаг в журнале: раскрывается в свои строки,
             у каждой справа карандаш; остальные настройки задаются окружением и только видны -->
        <table class="data-table fixed-columns settings-table">
          <colgroup>
            <col style="width: 280px" />
            <col />
            <col style="width: 92px" />
          </colgroup>
          <thead>
            <tr><th>Параметр</th><th>Значение</th><th></th></tr>
          </thead>
          <tbody>
            <template v-if="savedSolver">
              <tr class="group-row" @click="toggleGroup('cuopt')">
                <td>
                  <span class="twist">{{ openGroups.has('cuopt') ? '▾' : '▸' }}</span>
                  <strong>Решатель маршрутов</strong>
                  <InfoHint text="Общие параметры поиска для cuOpt и OR-Tools: их подставляет диалог расчёта, поменять на один расчёт можно прямо в нём" />
                </td>
                <td class="summary">{{ solverSummary }}</td>
                <td></td>
              </tr>
              <SolverParamRows
                v-if="openGroups.has('cuopt')"
                :values="savedSolver"
                :disabled="savingSolver"
                indent
                @update="saveOne"
              />
            </template>
            <!-- настройки окружения группами по службе («R5: …»): видны, но не правятся -->
            <template v-for="group in settingGroups.groups" :key="group.key">
              <tr class="group-row" @click="toggleGroup(group.key)">
                <td>
                  <span class="twist">{{ openGroups.has(group.key) ? '▾' : '▸' }}</span>
                  <strong>{{ group.title }}</strong>
                </td>
                <td class="summary">{{ group.summary }}</td>
                <td></td>
              </tr>
              <template v-if="openGroups.has(group.key)">
                <tr v-for="row in group.rows" :key="row.name" class="child-row">
                  <td class="child-name">{{ row.name }}</td>
                  <td class="target">{{ row.value }}</td>
                  <td></td>
                </tr>
              </template>
            </template>
            <!-- кеш ответов R5: сколько лежит; сбросить — после замены карты или расписания -->
            <tr v-if="travelCache" class="cache-row">
              <td>
                <strong>Кеш маршрутов R5</strong>
                <InfoHint
                  text="Матрица и плечи маршрутов общественного транспорта: одинаковые запросы R5 не считает второй раз. Записи старше срока удаляются раз в сутки, при смене расписания GTFS — все сразу. Сбросьте вручную, если заменили карту."
                />
              </td>
              <td class="summary">{{ travelCacheSummary }}</td>
              <td class="cache-action">
                <button
                  type="button"
                  class="link"
                  :disabled="clearingCache || (!travelCache.matrix_pairs && !travelCache.routes)"
                  @click="resetTravelCache"
                >
                  {{ clearingCache ? 'Сбрасываю…' : 'Сбросить' }}
                </button>
              </td>
            </tr>
            <tr v-for="row in settingGroups.plain" :key="row.name">
              <td>{{ row.name }}</td>
              <td class="target">{{ row.value }}</td>
              <td></td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="solverNotice" class="saved">{{ solverNotice }}</p>

      <h2 class="section-title">Данные</h2>
      <div class="counts">
        <article v-for="(count, name) in info.data" :key="name" class="count">
          <strong>{{ count }}</strong>
          <span>{{ name }}</span>
        </article>
      </div>

      <p class="muted">
        <button class="link" :disabled="loading" @click="load(); loadTravelCache()">{{ loading ? 'Обновляю…' : 'Обновить' }}</button>
      </p>
    </template>

  </div>
</template>

<style scoped>
.card-head {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.card-head h2 {
  margin: 0;
}

.demo-switch {
  display: flex;
  gap: 8px;
  align-items: center;
  color: #334155;
  font-size: 13px;
}

/* группа cuOpt раскрывается, как шаг в журнале расчёта */
.group-row {
  cursor: pointer;
}

.group-row:hover td {
  background: #eff6ff;
}

.twist {
  display: inline-block;
  width: 14px;
  color: #94a3b8;
}

/* текст параметров группы начинается ровно под её названием; селектор длиннее,
   потому что общий стиль ячеек таблицы сильнее */
.data-table.settings-table tbody td.child-name {
  padding-left: 27px;
}

.summary {
  color: #64748b;
  font-size: 12px;
}

.saved {
  color: #166534;
  font-size: 12px;
}

/* рабочая область — колонка flex: таблицы иначе сжимаются и обрезают строки */
.table-scroll {
  flex: none;
}

/* таблицы короткие: общий минимум ширины широких таблиц им не нужен */
.data-table.fixed-columns {
  min-width: 0;
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.card {
  padding: 12px 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.card.warn {
  border-color: #fcd34d;
  background: #fffbeb;
}

.card h2,
.section-title {
  margin: 0 0 8px;
  font-size: 15px;
}

.section-title {
  margin-top: 18px;
}

dl {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  font-size: 14px;
}

dl > div {
  display: flex;
  gap: 10px;
}

dt {
  flex-shrink: 0;
  width: 150px;
  color: #64748b;
}

dd {
  margin: 0;
}

.note {
  margin: 8px 0 0;
  color: #64748b;
  font-size: 12px;
}

.target {
  color: #334155;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  white-space: normal;
  word-break: break-all;
}

.badge.ok {
  background: #dcfce7;
  color: #166534;
}

.badge.fail {
  background: #fee2e2;
  color: #b91c1c;
}

.detail {
  margin-left: 8px;
  color: #64748b;
  font-size: 12px;
}

.counts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 10px;
}

.count {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fff;
}

.count strong {
  font-size: 20px;
}

.count span {
  color: #64748b;
  font-size: 12px;
}

/* «Сбросить» кеша — в колонке карандашей, по её правому краю */
.cache-action {
  text-align: right;
}
</style>
