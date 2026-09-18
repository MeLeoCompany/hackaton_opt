<script setup>
// Ячейки строки таблицы заявок в режиме редактирования (всё, кроме номера заявки).
// form — объект формы из useRequestsTable, поля ввода меняют его напрямую.
import DayTimeRange from './DayTimeRange.vue'
import EquipmentPicker from './EquipmentPicker.vue'
import IconButton from './IconButton.vue'
import PointPickerButton from './PointPickerButton.vue'

const props = defineProps({
  form: { type: Object, required: true },
  references: { type: Object, required: true },
  saving: { type: Boolean, required: true },
  // остальные заявки — показываем на карте выбора, чтобы было видно, где ставим новую
  contextPoints: { type: Array, default: () => [] },
})
const emit = defineEmits(['save', 'cancel', 'work-type-picked'])

function applyPickedPoint(latitude, longitude) {
  props.form.latitude = latitude
  props.form.longitude = longitude
}
</script>

<template>
  <td>
    <!-- тот же переключатель, что в обычной строке: при переходе в правку он не должен пропадать -->
    <label class="switch" :title="form.is_active ? 'Учитывается при планировании' : 'Не учитывается при планировании'">
      <input v-model="form.is_active" type="checkbox" />
      <span class="slider"></span>
    </label>
  </td>
  <td>
    <input v-model="form.address" class="wide-input" placeholder="Город Москва, ул. …" />
  </td>
  <td>
    <div class="coordinates-cell">
      <div class="coordinate-inputs">
        <input v-model="form.latitude" type="number" step="any" placeholder="широта" />
        <input v-model="form.longitude" type="number" step="any" placeholder="долгота" />
      </div>
      <PointPickerButton
        title="Где находится заявка"
        hint="Указать координаты на карте"
        :latitude="form.latitude"
        :longitude="form.longitude"
        :context-points="contextPoints"
        @pick="applyPickedPoint"
      />
    </div>
  </td>
  <td>
    <!-- оборудование живёт под типом работ: оно следует из работы, а своя колонка съела бы
         место у адреса -->
    <div class="work-type-cell">
      <select v-model="form.work_type_id" aria-label="тип работ" @change="emit('work-type-picked', form.work_type_id)">
        <option value="">не указан</option>
        <option v-for="item in references.work_types" :key="item.id" :value="item.id">{{ item.name }}</option>
      </select>
      <!-- что техник должен привезти и сколько: список с галочками, под ним количество -->
      <EquipmentPicker v-model="form.equipment" :options="references.equipment ?? []" empty-label="без оборудования" />
    </div>
  </td>
  <td>
    <input v-model="form.duration_minutes" type="number" min="1" class="short-input" />
  </td>
  <td>
    <DayTimeRange v-model:start="form.window_start" v-model:end="form.window_end" />
  </td>
  <td>
    <select v-model="form.priority_id">
      <option v-for="item in references.priorities" :key="item.id" :value="item.id">{{ item.name }}</option>
    </select>
  </td>
  <td>
    <select v-model="form.transport_id">
      <option value="">не важен</option>
      <option v-for="item in references.transports" :key="item.id" :value="item.id">{{ item.name }}</option>
    </select>
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



.work-type-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.coordinates-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.coordinate-inputs {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

</style>
