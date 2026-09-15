<script setup>
import { TRANSPORTS } from '../api/travelApi.js'

defineProps({
  transport: { type: Number, required: true },
  pointCount: { type: Number, required: true },
  canBuild: { type: Boolean, required: true },
  loading: { type: Boolean, required: true },
})
defineEmits(['update:transport', 'build-route', 'build-matrix', 'undo', 'clear'])
</script>

<template>
  <div class="controls">
    <label class="field">
      <span>Транспорт</span>
      <select
        :value="transport"
        @change="$emit('update:transport', Number($event.target.value))"
      >
        <option v-for="item in TRANSPORTS" :key="item.id" :value="item.id">
          {{ item.label }}
        </option>
      </select>
    </label>

    <div class="buttons">
      <button :disabled="!canBuild" @click="$emit('build-route')">
        {{ loading ? 'Считаю…' : 'Построить маршрут' }}
      </button>
      <button :disabled="!canBuild" @click="$emit('build-matrix')">Матрица</button>
      <button :disabled="pointCount === 0" @click="$emit('undo')">Убрать точку</button>
      <button :disabled="pointCount === 0" @click="$emit('clear')">Очистить</button>
    </div>

    <p class="hint">Кликайте по карте, чтобы поставить точки. Нужно минимум две.</p>
  </div>
</template>

<style scoped>
.controls {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
  color: #475569;
}

select {
  padding: 7px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 14px;
}

.buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

button {
  flex: 1 1 auto;
  padding: 8px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  background: #fff;
  font-size: 13px;
  cursor: pointer;
}

button:hover:not(:disabled) {
  border-color: #2563eb;
  color: #2563eb;
}

button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.hint {
  margin: 0;
  font-size: 12px;
  color: #94a3b8;
}
</style>
