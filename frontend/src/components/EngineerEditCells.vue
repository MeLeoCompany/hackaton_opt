<script setup>
// Ячейки строки таблицы исполнителей в режиме редактирования (всё, кроме номера).
// form — объект формы из useEngineersTable, поля ввода меняют его напрямую.
import { computed, ref } from 'vue'

import DayTimeRange from './DayTimeRange.vue'
import EquipmentPicker from './EquipmentPicker.vue'
import IconButton from './IconButton.vue'
import { isAtOffice } from '../utils/officePoint.js'
import PointPickerDialog from './PointPickerDialog.vue'
import StartPointIcon from './StartPointIcon.vue'

const props = defineProps({
  form: { type: Object, required: true },
  references: { type: Object, required: true },
  saving: { type: Boolean, required: true },
  // старты других бригад — ориентир на карте выбора
  contextPoints: { type: Array, default: () => [] },
})
const emit = defineEmits(['save', 'cancel'])

// офис бригады — это офис учётки: в справочниках формы он один
const office = computed(() => props.references.offices?.[0] ?? null)
const atOffice = computed(() => isAtOffice(props.form.start_latitude, props.form.start_longitude, office.value))

const startHint = computed(() => {
  if (atOffice.value) return `Из офиса «${office.value.name}». Нажмите, чтобы выбрать другую точку`
  const latitude = Number(props.form.start_latitude).toFixed(4)
  const longitude = Number(props.form.start_longitude).toFixed(4)
  return `Своя точка ${latitude}, ${longitude}. Нажмите, чтобы изменить или вернуть в офис`
})

// кнопка «В офис» в окне карты: вернуть старт в точку офиса одним нажатием
const officeHome = computed(() =>
  office.value
    ? { latitude: office.value.latitude, longitude: office.value.longitude, label: `В офис «${office.value.name}»` }
    : null,
)

const pickerOpen = ref(false)

function applyPickedPoint(latitude, longitude) {
  props.form.start_latitude = latitude
  props.form.start_longitude = longitude
  pickerOpen.value = false
}

// офис на карте выбора — рядом с ним обычно и ставят свою точку
const officeLandmarks = computed(() =>
  office.value
    ? [
        {
          latitude: office.value.latitude,
          longitude: office.value.longitude,
          label: `Офис «${office.value.name}» · ${office.value.address}`,
        },
      ]
    : [],
)

// бригады для выбора: работающие и та, чья эта смена уже есть (даже если её выключили)
const brigadeOptions = computed(() =>
  (props.references.brigades ?? []).filter((brigade) => brigade.is_active || brigade.id === props.form.brigade_id),
)
</script>

<template>
  <td>
    <!-- смена — бригады из справочника «Бригады»: новые — только работающим бригадам -->
    <select v-model="form.brigade_id" class="wide-input" aria-label="бригада">
      <option value="" disabled>выберите бригаду</option>
      <option v-for="brigade in brigadeOptions" :key="brigade.id" :value="brigade.id">
        {{ brigade.name }}{{ brigade.is_active ? '' : ' (выключена)' }}
      </option>
    </select>
  </td>
  <td>
    <select v-model="form.transport_id">
      <option v-for="item in references.transports" :key="item.id" :value="item.id">{{ item.name }}</option>
    </select>
  </td>
  <td>
    <div class="skill-checkboxes" title="От 1 до 3 навыков">
      <label v-for="skill in references.skills" :key="skill.id">
        <input v-model="form.skill_ids" type="checkbox" :value="skill.id" />
        {{ skill.name }}
      </label>
    </div>
  </td>
  <td>
    <!-- что бригада везёт и сколько: список с галочками, под ним количество -->
    <EquipmentPicker v-model="form.equipment" :options="references.equipment ?? []" empty-label="нет" />
  </td>
  <td>
    <DayTimeRange v-model:start="form.shift_start" v-model:end="form.shift_end" />
  </td>
  <td class="start-cell">
    <button type="button" class="start-button" :title="startHint" :aria-label="startHint" @click="pickerOpen = true">
      <StartPointIcon :at-office="atOffice" />
    </button>
    <PointPickerDialog
      v-if="pickerOpen"
      title="Откуда выезжает бригада"
      :latitude="form.start_latitude"
      :longitude="form.start_longitude"
      :context-points="contextPoints"
      :landmarks="officeLandmarks"
      :home="officeHome"
      @pick="applyPickedPoint"
      @close="pickerOpen = false"
    />
  </td>
  <td>
    <div class="row-actions">
      <IconButton
        icon="save"
        :label="saving ? 'Сохраняю…' : 'Сохранить'"
        variant="primary"
        :disabled="saving"
        @click="emit('save')"
      />
      <IconButton icon="cancel" label="Отмена" :disabled="saving" @click="emit('cancel')" />
    </div>
  </td>
</template>

<style scoped>
/* значок старта — кнопкой того же размера и на том же месте, что в просмотре строки:
   без своей рамки, кликабельность показывает тонкое кольцо, при наведении — ярче */
.start-button {
  display: inline-flex;
  width: 28px;
  min-width: 0;
  height: 24px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: none;
  line-height: 0;
  vertical-align: top;
  box-shadow: 0 0 0 1px #93c5fd;
  cursor: pointer;
}

.start-button:hover,
.start-button:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px #2563eb;
}





.skill-checkboxes {
  display: flex;
  flex-direction: column;
  gap: 4px;
}





.skill-checkboxes label {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  min-width: 0;
}

.skill-checkboxes input {
  flex-shrink: 0;
  width: 16px;
  min-width: 0;
  height: 16px;
  padding: 0;
}
</style>
