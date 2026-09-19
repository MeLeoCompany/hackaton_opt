<script setup>
import RouteControls from '../components/RouteControls.vue'
import RouteMap from '../components/RouteMap.vue'
import RouteSummary from '../components/RouteSummary.vue'
import { useRoutePlanner } from '../composables/useRoutePlanner.js'

const {
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
} = useRoutePlanner()
</script>

<template>
  <div class="layout">
    <aside class="panel">
      <header>
        <h1>Маршруты</h1>
        <p>Стенд для проверки расчёта расстояний и времени в пути</p>
      </header>

      <RouteControls
        v-model:transport="transport"
        :point-count="points.length"
        :can-build="canBuild"
        :loading="loading"
        @build-route="buildRoute"
        @build-matrix="buildMatrix"
        @undo="removeLastPoint"
        @clear="clear"
      />

      <p v-if="error" class="error">{{ error }}</p>

      <RouteSummary :route="route" :matrix="matrix" />
    </aside>

    <main class="map-area">
      <RouteMap :points="points" :route="route" @add-point="addPoint" />
    </main>
  </div>
</template>

<style scoped>
.layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  height: 100%;
}

.panel {
  padding: 16px;
  border-right: 1px solid #e2e8f0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel header h1 {
  margin: 0;
  font-size: 18px;
}

.panel header p {
  margin: 4px 0 0;
  font-size: 12px;
  color: #94a3b8;
}

/* карта стенда — во всю высоту страницы; общее правило .map-area в common.css задаёт
   фиксированную высоту для карт внутри рабочих областей, здесь она не нужна */
.map-area {
  position: relative;
  height: 100%;
  min-height: 0;
}

.error {
  margin: 0;
  padding: 8px 10px;
  border-radius: 6px;
  background: #fef2f2;
  color: #b91c1c;
  font-size: 12px;
}
</style>
