<script setup>
// Откуда выезжает бригада — значком: подсвеченное здание — из офиса (обычный случай),
// метка — из своей точки. Один и тот же значок в таблице и в строке правки.
defineProps({
  atOffice: { type: Boolean, required: true },
})
</script>

<template>
  <span :class="['start-icon', atOffice ? 'office' : 'own']" aria-hidden="true">
    <svg v-if="atOffice" viewBox="0 0 24 24" width="16" height="16">
      <path
        d="M4 21V8l8-5 8 5v13M9 21v-6h6v6M8 11h2M14 11h2"
        fill="none"
        stroke="currentColor"
        stroke-width="1.9"
        stroke-linecap="round"
        stroke-linejoin="round"
      />
    </svg>
    <svg v-else viewBox="0 0 24 24" width="16" height="16">
      <path
        d="M12 21s-6-6.2-6-11a6 6 0 0 1 12 0c0 4.8-6 11-6 11z"
        fill="none"
        stroke="currentColor"
        stroke-width="1.9"
        stroke-linejoin="round"
      />
      <circle cx="12" cy="10" r="2.3" fill="none" stroke="currentColor" stroke-width="1.9" />
    </svg>
  </span>
</template>

<style scoped>
.start-icon {
  display: inline-flex;
  vertical-align: top;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 24px;
  border-radius: 6px;
}

.start-icon.office {
  background: #dbeafe;
  color: #1d4ed8;
}

.start-icon.own {
  background: #f1f5f9;
  color: #475569;
}
</style>
