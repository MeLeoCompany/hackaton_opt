<script setup>
// Кнопка-значок для действий в строке таблицы: карандаш, корзина, галочка, крестик.
// Значок короче текста и читается быстрее; подпись видна при наведении и доступна скринридеру.
// Обработчик @click родителя вешается прямо на <button>, поэтому работают и модификаторы (.stop).
defineProps({
  icon: { type: String, required: true }, // edit | delete | save | cancel
  label: { type: String, required: true },
  variant: { type: String, default: '' }, // '' | primary | danger
})

const ICON_PATHS = {
  edit: 'M4 20h4L19 9l-4-4L4 16v4zM13.5 6.5l4 4',
  delete: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  save: 'M5 12.5l4.5 4.5L19 7.5',
  cancel: 'M6 6l12 12M18 6L6 18',
}
</script>

<template>
  <button type="button" :class="['icon-button', variant]" :title="label" :aria-label="label">
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path :d="ICON_PATHS[icon]" />
    </svg>
  </button>
</template>

<style scoped>
.icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  min-width: 0;
  height: 24px;
  padding: 0;
  color: #475569;
}

/* «Сохранить» — синяя кнопка с белым значком, как главные кнопки везде */
.icon-button.primary {
  color: #fff;
}
</style>
