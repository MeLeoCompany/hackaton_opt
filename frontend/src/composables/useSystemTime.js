// Системное время сервера — одно на все вкладки. Для демонстрации его можно перемотать:
// тогда пересчёт плана «с текущего момента», отметки бригад и опоздания считаются от него.
// Между запросами к серверу часы идут сами, раз в минуту время перечитывается.

import { computed, ref } from 'vue'

import { fetchSystemTime, setSystemTime } from '../api/systemApi.js'

const now = ref(new Date())
const offsetSeconds = ref(0)
const updatedBy = ref(null)
const loaded = ref(false)
const errorMessage = ref('')
let ticker = null
let sync = null

// расхождение часов браузера с сервером: прибавляем его к локальному времени между запросами
let serverShiftMs = 0

function applyServerTime(time) {
  serverShiftMs = new Date(time.now).getTime() - Date.now()
  offsetSeconds.value = time.offset_seconds
  updatedBy.value = time.updated_by
  loaded.value = true
  tick()
}

function tick() {
  now.value = new Date(Date.now() + serverShiftMs)
}

async function load() {
  try {
    applyServerTime(await fetchSystemTime())
    errorMessage.value = ''
  } catch (error) {
    errorMessage.value = error.message
  }
}

// вызывается один раз при входе: дальше часы идут сами
function start() {
  if (ticker) return
  load()
  ticker = setInterval(tick, 1000)
  sync = setInterval(load, 60_000)
}

function stop() {
  clearInterval(ticker)
  clearInterval(sync)
  ticker = null
  sync = null
  loaded.value = false
}

async function changeTime(payload) {
  errorMessage.value = ''
  try {
    applyServerTime(await setSystemTime(payload))
    return true
  } catch (error) {
    errorMessage.value = error.message
    return false
  }
}

export function useSystemTime() {
  return {
    now,
    offsetSeconds,
    updatedBy,
    loaded,
    errorMessage,
    // перемотано ли время: по нему интерфейс показывает предупреждение
    shifted: computed(() => offsetSeconds.value !== 0),
    start,
    stop,
    load,
    setMoment: (isoString) => changeTime({ now: isoString }),
    shiftBy: (seconds) => changeTime({ offset_seconds: offsetSeconds.value + seconds }),
    reset: () => changeTime({ offset_seconds: 0 }),
  }
}
