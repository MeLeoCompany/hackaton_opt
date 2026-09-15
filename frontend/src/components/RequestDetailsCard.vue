<script setup>
// Карточка выбранной на карте заявки.
import { formatMoscowWindow } from '../utils/moscowTime.js'
import { isUrgent, referenceName } from '../utils/referenceNames.js'

defineProps({
  request: { type: Object, default: null },
  references: { type: Object, required: true },
})
defineEmits(['show-in-table', 'close', 'toggle-active'])
</script>

<template>
  <section class="details">
    <template v-if="request">
      <header>
        <h2>Заявка №{{ request.id }}</h2>
        <button class="close" title="Снять выделение" @click="$emit('close')">×</button>
      </header>

      <p class="address">{{ request.address }}</p>

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
          <dt>Навык</dt>
          <dd>{{ referenceName(references, 'skills', request.skill_id) }}</dd>
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

      <div class="card-actions">
        <button class="primary" @click="$emit('show-in-table')">Показать в таблице</button>
        <button @click="$emit('toggle-active')">{{ request.is_active ? 'Выключить' : 'Включить' }}</button>
      </div>
    </template>

    <p v-else class="hint">Нажмите на точку на карте, чтобы увидеть заявку.</p>
  </section>
</template>

<style scoped>
.details {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 13px;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

h2 {
  margin: 0;
  font-size: 16px;
}

.close {
  padding: 0 8px;
  font-size: 18px;
  line-height: 26px;
}

.address {
  margin: 0;
  color: #334155;
}

dl {
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

dl > div {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

dt {
  color: #64748b;
}

dd {
  margin: 0;
  text-align: right;
}

.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  background: #f1f5f9;
  color: #334155;
}

.badge.urgent {
  background: #fee2e2;
  color: #b91c1c;
}

.status {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
}

.status.on {
  background: #dcfce7;
  color: #166534;
}

.status.off {
  background: #f1f5f9;
  color: #64748b;
}

.card-actions {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}

.card-actions button {
  flex: 1;
}

.hint {
  margin: 0;
  color: #94a3b8;
}
</style>
