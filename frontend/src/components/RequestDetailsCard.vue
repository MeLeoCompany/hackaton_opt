<script setup>
// Карточка заявки, выбранной на карте.
import { formatMoscowWindow } from '../utils/moscowTime.js'
import { isUrgent, referenceName } from '../utils/referenceNames.js'

defineProps({
  request: { type: Object, default: null },
  references: { type: Object, required: true },
})
defineEmits(['show-in-table', 'close', 'toggle-active'])
</script>

<template>
  <section class="details-card">
    <template v-if="request">
      <header>
        <h2>Заявка №{{ request.id }}</h2>
        <button class="close" title="Снять выделение" @click="$emit('close')">×</button>
      </header>

      <p class="muted">{{ request.address }}</p>

      <dl>
        <div>
          <dt>Планирование</dt>
          <dd>
            <span :class="['status', request.is_active ? 'on' : 'off']">
              {{ request.is_active ? 'Активна' : 'Выключена' }}
            </span>
          </dd>
        </div>
        <div>
          <dt>Окно (МСК)</dt>
          <dd>{{ formatMoscowWindow(request.window_start, request.window_end) }}</dd>
        </div>
        <div>
          <dt>Работа</dt>
          <dd>{{ request.duration_minutes }} мин</dd>
        </div>
        <div>
          <dt>Приоритет</dt>
          <dd>
            <span :class="['badge', { urgent: isUrgent(references, request) }]">
              {{ referenceName(references, 'priorities', request.priority_id) }}
            </span>
          </dd>
        </div>
        <div>
          <dt>Тип работ</dt>
          <dd>
            {{ referenceName(references, 'work_types', request.work_type_id) }}
            <span class="muted">· навык {{ referenceName(references, 'skills', request.skill_id) }}</span>
          </dd>
        </div>
        <div>
          <dt>Транспорт</dt>
          <dd>{{ referenceName(references, 'transports', request.transport_id) }}</dd>
        </div>
        <div>
          <dt>Координаты</dt>
          <dd>{{ request.latitude.toFixed(4) }}, {{ request.longitude.toFixed(4) }}</dd>
        </div>
      </dl>

      <div class="details-actions">
        <button class="primary" @click="$emit('show-in-table')">Показать в таблице</button>
        <button @click="$emit('toggle-active')">{{ request.is_active ? 'Выключить' : 'Включить' }}</button>
      </div>
    </template>

    <p v-else class="muted">Нажмите на точку на карте, чтобы увидеть заявку.</p>
  </section>
</template>

<style scoped>
p {
  margin: 0;
}
</style>
