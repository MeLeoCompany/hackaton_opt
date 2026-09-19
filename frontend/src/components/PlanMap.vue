<script setup>
// Карта плана — два вида.
//   Общий (исполнитель не выбран): маршрут каждой бригады своим цветом, пронумерованные точки
//   и — у утверждённого плана — значок бригады там, где она сейчас (по виду её транспорта).
//   Статусов здесь нет, чтобы не перегружать карту.
//   Выбранный маршрут: цвета — не бригады, а статусов. Выполнено — зелёное с ✓; участок, по
//   которому бригада едет (отметка «Выехали»), и заявка, к которой едет, — оранжевые, по участку
//   бегут стрелки; бригада на месте — голубая; впереди по плану — фиолетовое («В плане»), а
//   следующая заявка, пока бригада не выехала, — ярче и с пульсирующим кольцом; не выполненные
//   и снятые — серые.
//   На участках общественным транспортом — значки: пешком, автобус, метро, трамвай.
// Неназначенные заявки — серые точки.
// Клик по точке — карточка, в которой заявка ведёт в «Заявки», а бригада — на её маршрут.
// Клик по участку выбранного маршрута — карточка участка: откуда и куда, чем, сколько, план и факт.
// Клик по пустому месту карты снимает подсветку точки; к общему виду — только кнопкой
// «Все маршруты»: промахнуться мимо точки или участка легко, и маршрут бы пропадал.

import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { TRAVEL_MODES } from '../api/travelApi.js'
import { usePlanFocus } from '../composables/usePlanFocus.js'
import { runArrows } from '../utils/legArrows.js'
import { modeSvg, transportSvg } from '../utils/mapIcons.js'
import { moscowTimeOf } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { cumulativeLengths, lengthKm, offsetPath, pointAlong, travelledShare } from '../utils/pathGeometry.js'
import { decodePolyline } from '../utils/polyline.js'
import { routeColor } from '../utils/routeColors.js'
import { brigadeNow, visitFactState } from '../utils/routeFact.js'

const props = defineProps({
  plan: { type: Object, required: true },
  selectedEngineerId: { type: Number, default: null },
  // заявка, к которой перешли из «Заявок»: её точка крупнее, с обводкой и подписью
  focusedRequestId: { type: Number, default: null },
  references: { type: Object, default: () => ({}) },
  // утверждённый план: по нему ездят бригады — видно, где они и как идёт маршрут
  approved: { type: Boolean, default: false },
})
const emit = defineEmits(['select-engineer', 'focus-request'])

const { openRequest } = usePlanFocus()

const UNASSIGNED_COLOR = '#94a3b8'
// цвета статусов на выбранном маршруте — как у плашек статусов заявок (common.css)
const DONE_COLOR = '#16a34a' // «Выполнена»
const MOVING_COLOR = '#ea580c' // «В пути»: бригада выехала и едет
const ONSITE_COLOR = '#0284c7' // «В работе»: бригада на месте — голубой, чтобы не спутать с «в пути»
const PLANNED_COLOR = '#7c3aed' // «В плане»: впереди

// значки в легенде выбранного маршрута
const LEGEND_MODES = ['walk', 'bus', 'metro', 'tram']

// участок к визиту на выбранном маршруте — цветом статуса: пройден (доехали — значит, пройден
// и участок к заявке «на месте»), едут сейчас, берут следующим, впереди или к нему не поедут.
// Участки одной бригады часто идут по одной улице туда и обратно, поэтому, как на схеме метро,
// пройденные сдвинуты влево по ходу, будущие — вправо, текущий — посередине и поверх всех.
// rank — порядок рисования: больше — выше; offset — сдвиг вбок в пикселях
function legStyle(state, isNext, walk) {
  const dash = walk ? '2 8' : undefined
  if (state === 'moving') return { rank: 4, offset: 0, style: { color: MOVING_COLOR, weight: 7, opacity: 1, dashArray: dash } }
  // следующая по плану, бригада ещё не выехала — фиолетовый, но ярче и толще остальных впереди
  if (isNext && state === 'planned') {
    return { rank: 3, offset: 0, style: { color: PLANNED_COLOR, weight: 6, opacity: 1, dashArray: dash } }
  }
  if (state === 'done' || state === 'onsite') {
    return { rank: 2, offset: -5, style: { color: DONE_COLOR, weight: 4, opacity: 1, dashArray: dash } }
  }
  if (state === 'cancelled' || state === 'removed') {
    return { rank: 1, offset: 5, style: { color: UNASSIGNED_COLOR, weight: 3, opacity: 0.8, dashArray: '3 7' } }
  }
  return { rank: 0, offset: 5, style: { color: PLANNED_COLOR, weight: 3, opacity: 0.7, dashArray: dash } }
}

// точка визита на выбранном маршруте: ✓ выполнена, × не выполнена, номер — впереди
function progressVisitIcon(visit, state, focused, isNext) {
  if (state === 'done') return visitIcon('✓', DONE_COLOR, { focused })
  if (state === 'cancelled') return visitIcon('×', UNASSIGNED_COLOR, { focused })
  if (state === 'removed') return visitIcon(visit.visit_order, UNASSIGNED_COLOR, { focused })
  if (state === 'onsite') return visitIcon(visit.visit_order, ONSITE_COLOR, { focused, pulse: ONSITE_COLOR })
  if (state === 'moving') return visitIcon(visit.visit_order, MOVING_COLOR, { focused, pulse: MOVING_COLOR })
  if (isNext) return visitIcon(visit.visit_order, PLANNED_COLOR, { focused, pulse: PLANNED_COLOR })
  return visitIcon(visit.visit_order, PLANNED_COLOR, { focused, opacity: 0.8 })
}

// цвет значка бригады на выбранном маршруте — по тому, что она делает
function brigadeStateColor(kind) {
  if (kind === 'moving') return MOVING_COLOR
  if (kind === 'onsite') return ONSITE_COLOR
  if (kind === 'finished') return DONE_COLOR
  return '#334155'
}

const BRIGADE_SIZE = 30
const PIN_TAIL = 8
// на сколько поднять шпильку над точкой заявки или старта, чтобы не закрыть её номер
const PIN_LIFT = 9

function brigadeBadge(color, transportId) {
  return (
    `<span style="display:flex;align-items:center;justify-content:center;width:${BRIGADE_SIZE}px;` +
    `height:${BRIGADE_SIZE}px;box-sizing:border-box;border-radius:50%;background:#fff;border:3px solid ${color};` +
    `color:${color};box-shadow:0 2px 6px rgb(0 0 0 / 35%)">${transportSvg(transportId, 16)}</span>`
  )
}

// значок бригады — шпилька: кружок с транспортом (фургон, пешеход, велосипед, автобус) и хвостик
// вниз, к месту, где она сейчас. lift — стоит на точке заявки или старта: поднимаем над ней
function brigadePin(color, transportId, lift) {
  return L.divIcon({
    className: '',
    html:
      `<div style="position:relative;width:${BRIGADE_SIZE}px;height:${BRIGADE_SIZE + PIN_TAIL}px">` +
      brigadeBadge(color, transportId) +
      `<span style="position:absolute;left:${BRIGADE_SIZE / 2 - 6}px;top:${BRIGADE_SIZE - 2}px;width:0;height:0;` +
      `border-left:6px solid transparent;border-right:6px solid transparent;border-top:${PIN_TAIL + 2}px solid ${color}">` +
      `</span></div>`,
    iconSize: [BRIGADE_SIZE, BRIGADE_SIZE + PIN_TAIL],
    iconAnchor: [BRIGADE_SIZE / 2, BRIGADE_SIZE + PIN_TAIL + (lift ? PIN_LIFT : 0)],
  })
}

// несколько бригад в одной точке (не выехали из офиса) — веером над ней; dx, dy — сдвиг кружка
function brigadeFanned(color, transportId, dx, dy) {
  return L.divIcon({
    className: '',
    html: brigadeBadge(color, transportId),
    iconSize: [BRIGADE_SIZE, BRIGADE_SIZE],
    iconAnchor: [BRIGADE_SIZE / 2 - dx, BRIGADE_SIZE / 2 - dy],
  })
}

// сдвиги веера для n значков: дугой над точкой, соседи не перекрываются
function fanOffsets(count) {
  const radius = Math.max(26, (count * (BRIGADE_SIZE + 4)) / Math.PI)
  const spread = Math.min(Math.PI * 1.6, (count - 1) * 0.75)
  return Array.from({ length: count }, (_, index) => {
    const angle = -Math.PI / 2 + (count > 1 ? -spread / 2 + (spread * index) / (count - 1) : 0)
    return [Math.round(Math.cos(angle) * radius), Math.round(Math.sin(angle) * radius)]
  })
}

// плашка способа передвижения на участке: значок и номер маршрута автобуса / линии метро
function modeIcon(mode, routeId) {
  const style = TRAVEL_MODES[mode] ?? TRAVEL_MODES.transit
  const label = routeId ? `<b style="font:600 11px/1 system-ui,sans-serif">${escapeHtml(routeId)}</b>` : ''
  return L.divIcon({
    className: '',
    html:
      `<span style="display:inline-flex;align-items:center;gap:3px;height:22px;padding:0 5px;` +
      `border-radius:11px;background:${style.color};color:#fff;border:2px solid #fff;` +
      `box-shadow:0 1px 4px rgb(0 0 0 / 35%);white-space:nowrap">${modeSvg(mode, 13)}${label}</span>`,
    iconSize: null,
    iconAnchor: [11, 11],
  })
}

// точка на линии по доле пройденного пути; координаты — в плоском приближении (в пределах
// города искажение незаметно)
function pointOnLine(latlngs, share) {
  const scale = Math.cos((latlngs[0][0] * Math.PI) / 180)
  const flat = latlngs.map(([lat, lng]) => [lng * scale, lat])
  const lengths = cumulativeLengths(flat)
  const [x, y] = pointAlong(flat, lengths, lengths.at(-1) * share).point
  return [y, x / scale]
}

// выбранный маршрут и способы передвижения на нём — для легенды
const selectedRoute = computed(
  () => props.plan.routes.find((route) => route.engineer_id === props.selectedEngineerId) ?? null,
)
const selectedModes = computed(() => {
  const modes = new Set((selectedRoute.value?.legs ?? []).map((leg) => leg.mode))
  return LEGEND_MODES.filter((mode) => modes.has(mode))
})

// вернуться к общему виду: выбор бригады переключается повторным выбором той же бригады
function showAllRoutes() {
  if (props.focusedRequestId !== null) emit('focus-request', null)
  emit('select-engineer', props.selectedEngineerId)
}

const container = ref(null)
let map = null
let planLayer = null
// план, под который последний раз подгонялся масштаб
let fittedPlanId = null

// имена и адреса вводит человек — экранируем, прежде чем вставлять в HTML подсказки
function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (symbol) => `&#${symbol.charCodeAt(0)};`)
}

// точка визита: номер (или ✓ / ×) в кружке цвета маршрута; pulse — цвет пульсирующего кольца
function visitIcon(label, color, { focused = false, pulse = null, opacity = 1, small = false } = {}) {
  const size = focused ? 32 : small ? 20 : 22
  const ring = focused ? '0 0 0 4px #0f172a, 0 0 0 9px rgb(250 204 21 / 70%)' : '0 1px 3px rgb(0 0 0 / 40%)'
  return L.divIcon({
    className: pulse && !focused ? 'visit-pulse' : '',
    html:
      `<span style="display:flex;align-items:center;justify-content:center;width:${size}px;height:${size}px;` +
      `border-radius:50%;background:${color};color:#fff;font:600 ${focused ? 14 : 11}px/1 system-ui,sans-serif;` +
      `border:2px solid #fff;box-shadow:${ring};opacity:${opacity};--pulse:${pulse ?? color}">` +
      `${label}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

function routePoints(route) {
  return [[route.start_latitude, route.start_longitude], ...route.visits.map((visit) => [visit.latitude, visit.longitude])]
}

// линии маршрута, сгруппированные по визитам: к каждому — один или несколько кусков
// (общественным транспортом: пешком, автобус, пешком). Нет геометрии — прямая (straight)
function routeLegs(route) {
  const points = routePoints(route)
  if (route.geometry.length === 0) {
    return route.visits.map((visit, index) => [
      { latlngs: [points[index], points[index + 1]], details: null, straight: true },
    ])
  }
  const byVisit = route.visits.map(() => [])
  route.geometry.forEach((leg, legIndex) => {
    if (!leg) return
    const details = route.legs?.[legIndex] ?? null
    byVisit[details?.visit_index ?? legIndex]?.push({ latlngs: decodePolyline(leg), details, straight: false })
  })
  return byVisit
}

// какую заявку бригада берёт в работу: к которой едет, на которой стоит, иначе следующая
function activeVisitIndex(states) {
  const current = states.findIndex((state) => state === 'moving' || state === 'onsite')
  return current >= 0 ? current : states.indexOf('planned')
}

// где бригада сейчас: на заявке, на своём пути к ней (по времени в дороге) или там,
// где закрыла последнюю
function brigadePosition(route, now, legs) {
  if (now.kind === 'moving') {
    const pieces = legs[route.visits.indexOf(now.visit)] ?? []
    const latlngs = pieces.flatMap((piece) => piece.latlngs)
    const minutes = pieces.reduce((sum, piece) => sum + (piece.details?.duration_min ?? 0), 0)
    if (latlngs.length > 1) return pointOnLine(latlngs, travelledShare(now.visit.departed_at, minutes))
  }
  if (now.visit) return [now.visit.latitude, now.visit.longitude]
  return [route.start_latitude, route.start_longitude]
}

// маркер выделенной заявки: после подгонки масштаба у него открывается подпись
let focusedMarker = null
// остановка бегущих стрелок: при каждой перерисовке и уходе со страницы
let stopArrows = []

// линии, сдвинутые вбок: сдвиг задан в пикселях, поэтому при смене масштаба пересчитывается
let offsetLines = []

// сдвигаем только при крупном масштабе: там наложение участков и видно. На мелком точки линии
// сливаются, направление между ними скачет, и сдвинутая линия уходит от дороги
const OFFSET_MIN_ZOOM = 13
// точки ближе этого (в пикселях) выкидываем перед сдвигом — по той же причине
const OFFSET_MIN_STEP = 3

function shiftedLatLngs(latlngs, offset) {
  if (map.getZoom() < OFFSET_MIN_ZOOM) return latlngs
  const points = []
  latlngs.forEach((latlng, index) => {
    const { x, y } = map.latLngToLayerPoint(latlng)
    const last = points.at(-1)
    const isEnd = index === latlngs.length - 1
    if (!last || Math.hypot(x - last[0], y - last[1]) >= OFFSET_MIN_STEP) points.push([x, y])
    else if (isEnd && points.length > 1) points[points.length - 1] = [x, y]
  })
  return offsetPath(points, offset).map(([x, y]) => map.layerPointToLatLng(L.point(x, y)))
}

function addLine(latlngs, style, offset = 0) {
  // клик по линии не уходит на карту: там он возвращал бы к общему виду
  const line = L.polyline(offset ? shiftedLatLngs(latlngs, offset) : latlngs, {
    ...style,
    bubblingMouseEvents: false,
  }).addTo(planLayer)
  if (offset) offsetLines.push({ line, latlngs, offset })
  return line
}

function updateOffsetLines() {
  for (const { line, latlngs, offset } of offsetLines) line.setLatLngs(shiftedLatLngs(latlngs, offset))
}

function clearArrows() {
  stopArrows.forEach((stop) => stop())
  stopArrows = []
}

// кнопка-ссылка карточки точки: текст через textContent — адреса и имена вводит человек
function popupLink(text, title, onClick) {
  const link = document.createElement('button')
  link.type = 'button'
  link.className = 'map-popup-link'
  link.textContent = text
  link.title = title
  link.addEventListener('click', (event) => {
    event.stopPropagation()
    onClick()
  })
  return link
}

// карточка точки маршрута: заявка открывается в «Заявках», бригада — своим маршрутом
function visitPopup(route, visit) {
  const box = document.createElement('div')
  box.className = 'map-popup'
  const head = document.createElement('div')
  const time = document.createElement('b')
  time.textContent = `${visit.visit_order}. ${moscowTimeOf(visit.planned_arrival_time)}`
  head.append(time, ' · ', popupLink(`заявка №${visit.request_id}`, 'Открыть заявку в «Заявках»', () => openRequest(visit.request_id)))
  const address = document.createElement('div')
  address.textContent = visit.address
  // бригада — всегда ссылка: выбирает её маршрут, а уже выбранный показывает на карте целиком
  const brigade = popupLink(route.engineer_name, 'Показать маршрут бригады', () => {
    if (props.selectedEngineerId === route.engineer_id) fitTo(routePoints(route))
    else emit('select-engineer', route.engineer_id)
  })
  box.append(head, address, brigade)
  return box
}

// неназначенная заявка: номер ведёт в «Заявки», ниже — почему не назначена
function unassignedPopup(request) {
  const box = document.createElement('div')
  box.className = 'map-popup'
  const head = document.createElement('div')
  const title = document.createElement('b')
  title.textContent = 'Не назначена'
  head.append(title, ' · ', popupLink(`заявка №${request.request_id}`, 'Открыть заявку в «Заявках»', () => openRequest(request.request_id)))
  const address = document.createElement('div')
  address.textContent = request.address
  const reason = Object.assign(document.createElement('div'), { className: 'map-popup-muted', textContent: request.reason })
  box.append(head, address, reason)
  return box
}

// что происходит на участке — для карточки участка
const LEG_STATE_TEXT = {
  done: 'пройден',
  onsite: 'пройден, бригада на месте',
  moving: 'бригада едет сейчас',
  next: 'следующий: бригада ещё не выехала',
  planned: 'впереди по плану',
  cancelled: 'не поедут: заявка не выполнена',
  removed: 'не поедут: заявка снята с плана',
}

function popupRow(label, value) {
  const row = document.createElement('div')
  const name = Object.assign(document.createElement('span'), { className: 'map-popup-muted', textContent: `${label}: ` })
  row.append(name, value)
  return row
}

// карточка участка к визиту index: откуда и куда, чем и сколько ехать, план и факт.
// piece — кусок участка, по которому кликнули (у общественного транспорта их несколько)
function legPopup(route, index, piece, pieces, stateKey) {
  const visit = route.visits[index]
  const previous = index > 0 ? route.visits[index - 1] : null
  const box = document.createElement('div')
  box.className = 'map-popup'

  const head = document.createElement('div')
  const title = document.createElement('b')
  title.textContent = `Участок ${visit.visit_order}`
  head.append(
    title,
    ' · ',
    popupLink(route.engineer_name, 'Показать маршрут бригады целиком', () => fitTo(routePoints(route))),
  )

  const path = document.createElement('div')
  path.append(
    previous
      ? popupLink(`№${previous.request_id}`, 'Открыть заявку в «Заявках»', () => openRequest(previous.request_id))
      : 'старт',
    ' → ',
    popupLink(`№${visit.request_id}`, 'Открыть заявку в «Заявках»', () => openRequest(visit.request_id)),
  )

  // чем едут: у куска с режимом (общественный транспорт) — он, иначе транспорт бригады
  const mode = piece.details?.mode && piece.details.mode !== 'road' ? TRAVEL_MODES[piece.details.mode] : null
  const how = mode
    ? `${mode.label}${piece.details.route_id ? ` ${piece.details.route_id}` : ''}`
    : referenceName(props.references, 'transports', route.transport_id)
  const km = pieces.reduce((sum, item) => sum + (item.details?.distance_km ?? lengthKm(item.latlngs)), 0)
  const minutes = pieces.reduce((sum, item) => sum + (item.details?.duration_min ?? 0), 0)
  const wait = pieces.reduce((sum, item) => sum + (item.details?.wait_min ?? 0), 0)
  const travel =
    `${how} · ${km.toFixed(1)} км` +
    (minutes ? ` · ${Math.round(minutes)} мин в пути` : '') +
    (wait >= 1 ? ` · ожидание ${Math.round(wait)} мин` : '')

  box.append(
    head,
    path,
    popupRow('Как', travel),
    popupRow(
      'План',
      `свободна с ${moscowTimeOf(visit.available_from)}, начало работ ${moscowTimeOf(visit.planned_arrival_time)}`,
    ),
  )
  if (props.approved) {
    const fact = visit.departed_at
      ? `выехала ${moscowTimeOf(visit.departed_at)}` + (visit.arrived_at ? `, прибыла ${moscowTimeOf(visit.arrived_at)}` : ', в пути')
      : 'не выезжала'
    box.append(popupRow('Факт', fact), popupRow('Сейчас', LEG_STATE_TEXT[stateKey] ?? ''))
  }
  return box
}

// открытая карточка участка: клик по карте сначала просто закрывает её
let legPopupLayer = null
let legPopupWasOpen = false

function openLegPopup(latlng, content) {
  legPopupLayer = L.popup({ offset: [0, -4], maxWidth: 320 }).setLatLng(latlng).setContent(content).openOn(map)
}

const POPUP_OPTIONS = { closeButton: false, autoClose: false, closeOnClick: false, offset: [0, -8] }

function drawStart(route, color, select) {
  L.circleMarker([route.start_latitude, route.start_longitude], {
    radius: 7,
    color,
    weight: 3,
    fillColor: '#ffffff',
    fillOpacity: 1,
  })
    .bindTooltip(`Старт: <b>${escapeHtml(route.engineer_name)}</b>`, { direction: 'top' })
    .on('click', select)
    .addTo(planLayer)
}

function drawVisit(route, visit, icon, focused) {
  const marker = L.marker([visit.latitude, visit.longitude], { icon, zIndexOffset: focused ? 1000 : 0 })
  // у выделенной точки — карточка со ссылками, у остальных — подсказка при наведении
  if (focused) {
    marker.bindPopup(visitPopup(route, visit), POPUP_OPTIONS)
    focusedMarker = marker
  } else {
    marker.bindTooltip(
      `<b>${visit.visit_order}. ${moscowTimeOf(visit.planned_arrival_time)}</b> · заявка №${visit.request_id}<br>` +
        `${escapeHtml(visit.address)}<br>` +
        `<span style="color:#64748b">${escapeHtml(route.engineer_name)}</span>`,
      { direction: 'top', offset: [0, -8] },
    )
  }
  // клик по точке — подсветка и карточка переходят на эту заявку; маршрут не меняется
  marker.on('click', () => emit('focus-request', visit.request_id)).addTo(planLayer)
}

// где бригада и каким цветом её рисовать: color — цвет бригады (общий вид), без него — цвет
// её состояния (выбранный маршрут). Рисуются все вместе в drawBrigades
function brigadeMark(route, color, legs, select) {
  const now = brigadeNow(route, props.references, props.plan.id)
  return {
    route,
    now,
    select,
    color: color ?? brigadeStateColor(now.kind),
    position: brigadePosition(route, now, legs),
  }
}

// бригады в одной точке (не выехали из офиса, стоят на одной заявке) раскладываются веером,
// одиночная — шпилька к своему месту
function drawBrigades(marks) {
  const groups = new Map()
  for (const mark of marks) {
    const key = mark.position.map((value) => value.toFixed(5)).join(',')
    groups.set(key, [...(groups.get(key) ?? []), mark])
  }
  for (const group of groups.values()) {
    const offsets = fanOffsets(group.length)
    group.forEach((mark, index) => {
      const [dx, dy] = offsets[index]
      const icon =
        group.length > 1
          ? brigadeFanned(mark.color, mark.route.transport_id, dx, dy)
          : brigadePin(mark.color, mark.route.transport_id, mark.now.kind !== 'moving')
      const top = group.length > 1 ? dy - BRIGADE_SIZE / 2 : -(BRIGADE_SIZE + PIN_TAIL + PIN_LIFT)
      L.marker(mark.position, { icon, zIndexOffset: 2000 })
        .bindTooltip(`<b>${escapeHtml(mark.route.engineer_name)}</b><br>${escapeHtml(mark.now.text)}`, {
          direction: 'top',
          offset: [group.length > 1 ? dx : 0, top],
        })
        .on('click', mark.select)
        .addTo(planLayer)
    })
  }
}

// общий вид: только маршрут цветом бригады, номера точек и где бригада — без статусов
function drawRouteOverview(route, color, select) {
  const legs = routeLegs(route)
  for (const piece of legs.flat()) {
    const dashArray = piece.straight ? '8 8' : piece.details?.mode === 'walk' ? '2 8' : undefined
    L.polyline(piece.latlngs, { color, weight: 4, opacity: 0.85, dashArray, bubblingMouseEvents: false })
      .bindTooltip(escapeHtml(route.engineer_name))
      .on('click', select)
      .addTo(planLayer)
  }
  drawStart(route, color, select)
  for (const visit of route.visits) {
    const focused = visit.request_id === props.focusedRequestId
    drawVisit(route, visit, visitIcon(visit.visit_order, color, { focused, small: true }), focused)
  }
  return props.approved ? brigadeMark(route, color, legs, select) : null
}

// выбранный маршрут: ход работы по отметкам бригады и способ передвижения на участках
function drawRouteProgress(route, select) {
  const legs = routeLegs(route)
  const states = route.visits.map((visit) =>
    props.approved ? visitFactState(visit, props.references, props.plan.id) : 'planned',
  )
  const activeIndex = props.approved ? activeVisitIndex(states) : -1

  const lines = []
  legs.forEach((pieces, index) => {
    for (const { latlngs, details, straight } of pieces) {
      const walk = details?.mode === 'walk'
      const look = props.approved
        ? legStyle(states[index], index === activeIndex, walk)
        : {
            rank: 0,
            offset: 0,
            style: { color: PLANNED_COLOR, weight: 5, opacity: 0.8, dashArray: straight ? '8 8' : walk ? '2 8' : undefined },
          }
      const mode = details?.mode && details.mode !== 'road' ? TRAVEL_MODES[details.mode] : null
      const label = mode
        ? `${mode.label}${details.route_id ? ` · ${escapeHtml(details.route_id)}` : ''}`
        : escapeHtml(route.engineer_name)
      const stateKey = states[index] === 'planned' && index === activeIndex ? 'next' : states[index]
      lines.push({
        latlngs,
        label,
        moving: props.approved && states[index] === 'moving',
        popup: () => legPopup(route, index, { latlngs, details }, pieces, stateKey),
        ...look,
      })
      // способ передвижения на участке: значок чуть отступя от начала поездки (чтобы не закрыть
      // точку заявки), пешком — посередине; под точками заявок, над стрелками
      if (mode && details.mode !== 'walk' && latlngs.length > 1) {
        L.marker(pointOnLine(latlngs, 0.2), { icon: modeIcon(details.mode, details.route_id), zIndexOffset: -500 })
          .bindTooltip(label)
          .addTo(planLayer)
      } else if (walk && (details.distance_km ?? 0) >= 0.15 && latlngs.length > 1) {
        L.marker(pointOnLine(latlngs, 0.5), { icon: modeIcon('walk'), zIndexOffset: -500 })
          .bindTooltip(`${label} · ${Math.round(details.duration_min)} мин`)
          .addTo(planLayer)
      }
    }
  })
  // снизу вверх: будущие, снятые, пройденные, следующий, текущий
  lines.sort((first, second) => first.rank - second.rank)
  for (const line of lines) {
    addLine(line.latlngs, line.style, line.offset)
      .bindTooltip(`${line.label} · нажмите — подробности`)
      .on('click', (event) => openLegPopup(event.latlng, line.popup()))
    // по этому участку бригада едет сейчас — стрелки бегут к заявке
    if (line.moving) stopArrows.push(runArrows(map, planLayer, line.latlngs))
  }

  drawStart(route, '#334155', select)
  route.visits.forEach((visit, index) => {
    const focused = visit.request_id === props.focusedRequestId
    const icon = props.approved
      ? progressVisitIcon(visit, states[index], focused, index === activeIndex)
      : visitIcon(visit.visit_order, PLANNED_COLOR, { focused })
    drawVisit(route, visit, icon, focused)
  })
  return props.approved ? brigadeMark(route, null, legs, select) : null
}

function drawPlan() {
  clearArrows()
  planLayer.clearLayers()
  focusedMarker = null
  offsetLines = []
  const brigades = []

  // выбран исполнитель — рисуем только его маршрут: с десятком маршрутов карта иначе тормозит
  props.plan.routes.forEach((route, routeIndex) => {
    const color = routeColor(routeIndex)
    // клик по линии, старту, значку бригады — выбрать её маршрут; уже выбранный не снимается
    const select = () => {
      if (props.selectedEngineerId !== route.engineer_id) emit('select-engineer', route.engineer_id)
    }
    const mark =
      props.selectedEngineerId === null
        ? drawRouteOverview(route, color, select)
        : props.selectedEngineerId === route.engineer_id
          ? drawRouteProgress(route, select)
          : null
    if (mark) brigades.push(mark)
  })
  drawBrigades(brigades)

  // неназначенные — в общем виде: на выбранном маршруте они только мешают
  if (props.selectedEngineerId === null) {
    for (const request of props.plan.unassigned) {
      L.circleMarker([request.latitude, request.longitude], {
        radius: 6,
        color: '#ffffff',
        weight: 1.5,
        fillColor: UNASSIGNED_COLOR,
        fillOpacity: 0.9,
      })
        .bindTooltip(
          `<b>Не назначена</b> · заявка №${request.request_id}<br>${escapeHtml(request.address)}<br>` +
            `<span style="color:#64748b">${escapeHtml(request.reason)}</span>`,
          { direction: 'top' },
        )
        // по клику — та же карточка, но номер заявки в ней кликабелен
        .bindPopup(unassignedPopup(request), { closeButton: false, offset: [0, -4] })
        .on('popupopen', (event) => event.target.closeTooltip())
        .addTo(planLayer)
    }
  }

  // масштаб подгоняем только при смене плана — при выборе исполнителя карта не прыгает
  if (fittedPlanId !== props.plan.id) {
    fittedPlanId = props.plan.id
    // открыли план сразу на маршруте бригады (переход из заявки) — масштаб по этому маршруту
    const selectedRoute = props.plan.routes.find((route) => route.engineer_id === props.selectedEngineerId)
    fitTo(
      selectedRoute
        ? routePoints(selectedRoute)
        : [
            ...props.plan.routes.flatMap(routePoints),
            ...props.plan.unassigned.map((request) => [request.latitude, request.longitude]),
          ],
    )
  }
  focusedMarker?.openPopup()
}

function fitTo(points) {
  const bounds = L.latLngBounds(points)
  if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 })
}

// выбрали исполнителя — остаётся только его маршрут; сняли выбор — возвращаются все
function showSelectedRoute() {
  drawPlan()
  const selectedRoute = props.plan.routes.find((route) => route.engineer_id === props.selectedEngineerId)
  fitTo(
    selectedRoute
      ? routePoints(selectedRoute)
      : [
          ...props.plan.routes.flatMap(routePoints),
          ...props.plan.unassigned.map((request) => [request.latitude, request.longitude]),
        ],
  )
}

onMounted(async () => {
  map = L.map(container.value).setView([55.751244, 37.618423], 10)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 19,
  }).addTo(map)
  planLayer = L.layerGroup().addTo(map)
  map.on('zoomend', updateOffsetLines)
  // открылась карточка (точки, участка, неназначенной заявки) — подсказки закрываем: Leaflet
  // открывает их и по клику, и они висели бы рядом с карточкой, пока мышь не уйдёт
  map.on('popupopen', () => planLayer.eachLayer((layer) => layer.closeTooltip?.()))
  // клик по пустому месту карты снимает подсветку заявки; маршрут остаётся выбранным.
  // Точки и линии клик к карте сами не пропускают
  // открытую карточку участка Leaflet закрывает ещё до click — запоминаем её заранее
  map.on('preclick', () => {
    legPopupWasOpen = legPopupLayer !== null && map.hasLayer(legPopupLayer)
  })
  map.on('click', () => {
    if (legPopupWasOpen) return
    if (props.focusedRequestId !== null) emit('focus-request', null)
  })

  await nextTick()
  map.invalidateSize()
  drawPlan()
})

onBeforeUnmount(() => {
  clearArrows()
  map?.remove()
})

watch(() => props.plan, drawPlan)
watch(() => props.selectedEngineerId, showSelectedRoute)
// подсветку перенесли кликом в карточке маршрута — точка могла оказаться за краем карты
function showFocused() {
  drawPlan()
  if (focusedMarker && !map.getBounds().contains(focusedMarker.getLatLng())) map.panTo(focusedMarker.getLatLng())
}

watch(() => props.focusedRequestId, showFocused)
watch(() => props.approved, drawPlan)
</script>

<template>
  <div class="map-frame">
    <div ref="container" class="map"></div>
    <button v-if="selectedRoute" type="button" class="map-back" title="Вернуться к общему плану" @click="showAllRoutes">
      ← Все маршруты
    </button>
    <!-- выбранный маршрут утверждённого плана: как идёт работа -->
    <div v-if="selectedRoute && approved" class="map-legend">
      <span><i class="legend-dot" :style="{ background: DONE_COLOR }"></i>выполнено</span>
      <span><i class="legend-line moving" :style="{ background: MOVING_COLOR }"></i>едет сейчас</span>
      <span><i class="legend-dot" :style="{ background: ONSITE_COLOR }"></i>на месте</span>
      <span><i class="legend-line" :style="{ background: PLANNED_COLOR, opacity: 0.6 }"></i>впереди по плану</span>
      <span><i class="legend-dot" :style="{ background: UNASSIGNED_COLOR }"></i>не выполнена, снята</span>
      <span v-for="mode in selectedModes" :key="mode">
        <i class="legend-mode" :style="{ background: TRAVEL_MODES[mode].color }" v-html="modeSvg(mode, 11)"></i
        >{{ TRAVEL_MODES[mode].label.toLowerCase() }}
      </span>
    </div>
    <div v-else-if="selectedRoute" class="map-legend">
      <span><i class="legend-dot start-dot"></i>старт исполнителя</span>
      <span><i class="legend-line" :style="{ background: PLANNED_COLOR, opacity: 0.8 }"></i>маршрут по плану</span>
      <span class="muted">цифра — порядок визита</span>
      <span v-for="mode in selectedModes" :key="mode">
        <i class="legend-mode" :style="{ background: TRAVEL_MODES[mode].color }" v-html="modeSvg(mode, 11)"></i
        >{{ TRAVEL_MODES[mode].label.toLowerCase() }}
      </span>
    </div>
    <!-- общий вид: только бригады и их маршруты -->
    <div v-else class="map-legend">
      <span class="muted">цвет — маршрут бригады</span>
      <span v-if="approved"><span class="legend-van" v-html="transportSvg(1, 16)"></span>где бригада сейчас</span>
      <span><i class="legend-dot start-dot"></i>старт</span>
      <span><i class="legend-dot" :style="{ background: UNASSIGNED_COLOR }"></i>не назначена</span>
      <span class="muted">выберите маршрут — покажется ход работы</span>
    </div>
  </div>
</template>

<!-- анимации факта: Leaflet рисует линии и значки вне компонента, поэтому стили не scoped -->
<style>
/* заявка, которую бригада берёт в работу, — пульсирующее кольцо цвета её маршрута (--pulse) */
.visit-pulse > span {
  animation: visit-pulse 1.6s ease-out infinite;
}

@keyframes visit-pulse {
  0% {
    box-shadow: 0 0 0 0 var(--pulse);
  }
  100% {
    box-shadow: 0 0 0 14px transparent;
  }
}

/* карточка точки: номер заявки и бригада — ссылки */
.map-popup {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
  line-height: 1.4;
}

.map-popup-link {
  padding: 0;
  border: none;
  background: none;
  color: #1d4ed8;
  font: inherit;
  text-align: left;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}

.map-popup-link:hover {
  color: #1e40af;
}

.map-popup-muted {
  color: #64748b;
}

.leaflet-popup-content {
  margin: 10px 12px;
}

/* клик по линии даёт ей фокус, и браузер обводит рамкой всю её огромную область */
.leaflet-interactive:focus {
  outline: none;
}

/* бегущие стрелки не ловят мышь: подсказки остаются у линии под ними */
.leg-arrow {
  pointer-events: none;
}

@media (prefers-reduced-motion: reduce) {
  .visit-pulse > span {
    animation: none;
  }
}
</style>

<style scoped>
.map-back {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 1000;
  padding: 6px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #fff;
  color: #1d4ed8;
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 2px 6px rgb(0 0 0 / 15%);
}

.map-back:hover {
  background: #eff6ff;
}

.legend-van {
  display: inline-flex;
  margin-right: 4px;
  vertical-align: middle;
  color: #334155;
}

.legend-line {
  display: inline-block;
  width: 18px;
  height: 5px;
  margin-right: 5px;
  border-radius: 3px;
  vertical-align: middle;
}

/* «едет сейчас» — полоса со стрелкой, как на карте */
.legend-line.moving {
  position: relative;
}

.legend-line.moving::after {
  content: '›';
  position: absolute;
  top: -6px;
  left: 6px;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.legend-mode {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 17px;
  height: 17px;
  margin-right: 4px;
  border-radius: 50%;
  color: #fff;
  vertical-align: middle;
}

.start-dot {
  background: #fff;
  box-shadow: 0 0 0 2px #334155;
}
</style>
