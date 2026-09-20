// Ход текущего расчёта: интерфейс придумывает номер запуска заранее, отдаёт его вместе
// с параметрами расчёта и опрашивает журнал, пока расчёт идёт. Без этого большой день
// выглядит зависшим: матрицы и решатель работают минутами (docs/algoV2.md, «Журнал»).

import { ref } from 'vue'

import { fetchPlanRun } from '../api/systemApi.js'

const POLL_MS = 800

export function usePlanRun() {
  const run = ref(null) // последний известный ответ журнала; null — расчёт не идёт
  let timer = null
  let watched = null

  // crypto.randomUUID есть только на https и localhost, а стенд открывают по IP —
  // поэтому собираем UUID v4 сами, иначе бэкенд отвергает номер запуска
  function newRunId() {
    const bytes = new Uint8Array(16)
    if (window.crypto?.getRandomValues) window.crypto.getRandomValues(bytes)
    else for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256)
    bytes[6] = (bytes[6] & 0x0f) | 0x40 // версия 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80 // вариант
    const hex = [...bytes].map((byte) => byte.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
  }

  async function poll() {
    if (!watched) return
    try {
      const fresh = await fetchPlanRun(watched)
      if (watched) run.value = fresh
    } catch {
      // журнал — подсказка, а не работа: расчёт идёт дальше, даже если его не видно
    }
  }

  // начали расчёт: показываем шаги, пока не остановим
  function watch(runId) {
    stop()
    watched = runId
    run.value = null
    timer = setInterval(poll, POLL_MS)
    poll()
  }

  function stop() {
    clearInterval(timer)
    timer = null
    watched = null
    run.value = null
  }

  return { run, newRunId, watch, stop }
}
