<script setup>
// Ползунок «Зона покрытия» в углу карты: показать, где выгружены дороги и расписания.
// Переключатель — общий для всего приложения (styles/common.css, .switch), как у бригад
// и учёток: своего не рисуем, иначе на карте появился бы ещё один вид ползунка.
// Состояние общее для всех карт — включил в заявках, увидел и в маршрутах, и при выборе точки.
import { COVERAGE_AREAS, COVERAGE_HINT } from '../utils/coverageLayer.js'
import { useCoverage } from '../composables/useCoverage.js'

const { shown } = useCoverage()
</script>

<template>
  <label class="coverage-toggle" :title="`${COVERAGE_HINT} · зон: ${COVERAGE_AREAS}`">
    <span class="switch">
      <input v-model="shown" type="checkbox" />
      <span class="slider"></span>
    </span>
    <span class="caption">Зона покрытия</span>
  </label>
</template>

<style scoped>
.coverage-toggle {
  position: absolute;
  z-index: 500; /* над картой, под всплывающими окнами Leaflet */
  top: 10px;
  right: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px 6px 8px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: rgb(255 255 255 / 94%);
  box-shadow: 0 1px 4px rgb(15 23 42 / 18%);
  color: #334155;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}

.caption {
  white-space: nowrap;
}
</style>
