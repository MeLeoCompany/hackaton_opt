<script setup>
// Карточка исполнителя, выбранного на карте.
import { formatMoscowWindow } from '../utils/moscowTime.js'
import { referenceName } from '../utils/referenceNames.js'
import { transportColor } from '../utils/transportColors.js'

defineProps({
  engineer: { type: Object, default: null },
  references: { type: Object, required: true },
})
defineEmits(['show-in-table', 'close'])
</script>

<template>
  <section class="details-card">
    <template v-if="engineer">
      <header>
        <h2>{{ engineer.name }}</h2>
        <button class="close" title="Снять выделение" @click="$emit('close')">×</button>
      </header>

      <dl>
        <div>
          <dt>Номер</dt>
          <dd>{{ engineer.id }}</dd>
        </div>
        <div>
          <dt>Транспорт</dt>
          <dd>
            <i class="legend-dot" :style="{ background: transportColor(engineer.transport_id) }"></i>
            {{ referenceName(references, 'transports', engineer.transport_id) }}
          </dd>
        </div>
        <div>
          <dt>Смена (МСК)</dt>
          <dd>{{ formatMoscowWindow(engineer.shift_start, engineer.shift_end) }}</dd>
        </div>
        <div>
          <dt>Навыки</dt>
          <dd>
            <div class="chips skills">
              <span v-for="skillId in engineer.skill_ids" :key="skillId" class="badge">
                {{ referenceName(references, 'skills', skillId) }}
              </span>
            </div>
          </dd>
        </div>
        <div>
          <dt>Оборудование</dt>
          <dd>
            <template v-if="engineer.equipment?.length">
              <span v-for="item in engineer.equipment" :key="item.equipment_id" class="equipment-badge">
                ⚙ {{ referenceName(references, 'equipment', item.equipment_id) }} × {{ item.quantity }}
              </span>
            </template>
            <template v-else>нет</template>
          </dd>
        </div>
        <div>
          <dt>Старт</dt>
          <dd>
            <template v-if="engineer.start_at_office">
              Офис «{{ referenceName(references, 'offices', engineer.office_id) }}» ·
            </template>
            {{ engineer.start_latitude.toFixed(4) }}, {{ engineer.start_longitude.toFixed(4) }}
          </dd>
        </div>
      </dl>

      <div class="details-actions">
        <button class="primary" @click="$emit('show-in-table')">Показать в таблице</button>
      </div>
    </template>

    <p v-else class="muted">Нажмите на точку на карте, чтобы увидеть исполнителя.</p>
  </section>
</template>

<style scoped>
p {
  margin: 0;
}

/* навыки столбиком по правому краю: длинный навык переносится внутри своей плашки
   и не залезает на подпись слева */
.skills {
  flex-direction: column;
  align-items: flex-end;
}

.skills .badge {
  max-width: 100%;
  white-space: normal;
  text-align: right;
}
</style>
