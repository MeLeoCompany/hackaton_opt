<script setup>
// Значок «i»: при наведении (или фокусе с клавиатуры) показывает пояснение.
defineProps({
  text: { type: String, required: true },
})
</script>

<template>
  <span class="info-hint" tabindex="0" :aria-label="text">
    <span aria-hidden="true">i</span>
    <span class="bubble" role="tooltip">{{ text }}</span>
  </span>
</template>

<style scoped>
.info-hint {
  position: relative;
  display: inline-grid;
  place-items: center;
  width: 16px;
  height: 16px;
  margin-left: 6px;
  border: 1px solid #94a3b8;
  border-radius: 50%;
  color: #64748b;
  font-size: 11px;
  font-style: italic;
  font-weight: 700;
  line-height: 1;
  vertical-align: middle;
  cursor: help;
}

.info-hint:hover,
.info-hint:focus {
  border-color: #2563eb;
  color: #2563eb;
  outline: none;
}

.bubble {
  position: absolute;
  top: calc(100% + 6px);
  left: -8px;
  z-index: 50;
  width: 300px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #0f172a;
  color: #f8fafc;
  font-size: 12px;
  font-style: normal;
  font-weight: 400;
  line-height: 1.45;
  white-space: normal;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.12s;
}

.info-hint:hover .bubble,
.info-hint:focus .bubble {
  opacity: 1;
}
</style>
