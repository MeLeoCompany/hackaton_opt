<script setup>
// Панель групповых действий: появляется, как только в таблице отмечена хотя бы одна строка.
// Снять отметки нечем нарочно: это делает «Сбросить» в строке фильтров — там же, где
// снимается всё остальное, чем сужен список.
defineProps({
  count: { type: Number, required: true },
  title: { type: String, required: true }, // «заявка/заявки/заявок» уже посчитанное
  busy: { type: Boolean, default: false },
})
defineEmits(['edit', 'delete'])
</script>

<template>
  <section class="bulk-bar" role="region" aria-label="Действия с отмеченными строками">
    <strong>Отмечено: {{ title }}</strong>
    <slot />
    <button :disabled="busy" @click="$emit('edit')">Изменить</button>
    <button class="danger" :disabled="busy" @click="$emit('delete')">Удалить</button>
  </section>
</template>

<style scoped>
.bulk-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 8px 12px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: #eff6ff;
}

.bulk-bar strong {
  margin-right: 4px;
  color: #1e3a8a;
  font-size: 14px;
}
</style>
