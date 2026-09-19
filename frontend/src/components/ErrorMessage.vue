<script setup>
// Ошибка на странице: заголовок и список причин. Крестиком её можно убрать, не дожидаясь
// следующего действия. Вместо простого списка можно передать своё содержимое (слот).
defineProps({
  message: { type: String, required: true },
  details: { type: Array, default: () => [] },
})
defineEmits(['close'])
</script>

<template>
  <div class="message error" role="alert">
    <button type="button" class="message-close" title="Закрыть" aria-label="Закрыть ошибку" @click="$emit('close')">
      ×
    </button>
    <strong>{{ message }}</strong>
    <ul v-if="details.length">
      <li v-for="(detail, index) in details" :key="index">{{ detail }}</li>
    </ul>
    <slot />
  </div>
</template>

<style scoped>
.message {
  position: relative;
  padding-right: 40px;
}

.message-close {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 26px;
  min-width: 0;
  height: 26px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #991b1b;
  font-size: 18px;
  line-height: 26px;
  cursor: pointer;
}

.message-close:hover {
  background: #fee2e2;
}
</style>
