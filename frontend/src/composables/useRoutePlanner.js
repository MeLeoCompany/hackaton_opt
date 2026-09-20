import { computed, ref } from 'vue'

import { fetchMatrix, fetchRoute } from '../api/travelApi.js'

export function useRoutePlanner() {
  const points = ref([])
  const transport = ref(1)
  const route = ref(null)
  const matrix = ref(null)
  const error = ref('')
  const loading = ref(false)

  const canBuild = computed(() => points.value.length >= 2 && !loading.value)

  function addPoint(latitude, longitude) {
    points.value.push({ latitude, longitude })
    route.value = null
    matrix.value = null
  }

  function removeLastPoint() {
    points.value.pop()
    route.value = null
    matrix.value = null
  }

  function clear() {
    points.value = []
    route.value = null
    matrix.value = null
    error.value = ''
  }

  async function run(request, target) {
    if (points.value.length < 2) return
    loading.value = true
    error.value = ''
    try {
      // время выезда — системное: у общественного транспорта от него зависит расписание,
      // а перематывают его часами в правом верхнем углу
      target.value = await request(points.value, transport.value)
    } catch (e) {
      error.value = e.message
      target.value = null
    } finally {
      loading.value = false
    }
  }

  const buildRoute = () => run(fetchRoute, route)
  const buildMatrix = () => run(fetchMatrix, matrix)

  return {
    points,
    transport,
    route,
    matrix,
    error,
    loading,
    canBuild,
    addPoint,
    removeLastPoint,
    clear,
    buildRoute,
    buildMatrix,
  }
}
