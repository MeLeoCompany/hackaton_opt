<script setup>
// Карточка заявки, выбранной на карте.
import { formatMoscowWindow } from '../utils/moscowTime.js'
import { isUrgent, referenceName } from '../utils/referenceNames.js'
import RequestStatusMenu from './RequestStatusMenu.vue'

defineProps({
  request: { type: Object, default: null },
  references: { type: Object, required: true },
})
defineEmits(['show-in-table', 'close', 'change-status', 'history', 'open-plan'])
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
          <dt>Статус</dt>
          <dd>
            <RequestStatusMenu
              :status-id="request.status_id"
              :references="references"
              :plan-id="request.approved_plan_id ?? null"
              @change="$emit('change-status', $event)"
              @history="$emit('history')"
              @open-plan="$emit('open-plan')"
            />
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
          <dd>{{ referenceName(references, 'work_types', request.work_type_id) }}</dd>
        </div>
        <div>
          <dt>Оборудование</dt>
          <dd>
            <template v-if="request.equipment?.length">
              <span v-for="item in request.equipment" :key="item.equipment_id" class="equipment-badge">
                ⚙ {{ referenceName(references, 'equipment', item.equipment_id) }} × {{ item.quantity }}
              </span>
            </template>
            <template v-else>не нужно</template>
          </dd>
        </div>
        <div>
          <dt>Навык</dt>
          <dd>
            <span class="badge">{{ referenceName(references, 'skills', request.skill_id) }}</span>
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
