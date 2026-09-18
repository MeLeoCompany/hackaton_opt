<script setup>
// Справочник офисов: откуда бригады выезжают на смену. Добавить, изменить, удалить.
// День здесь не нужен: справочники общие на все дни, поэтому полосы дня на странице нет.
import { computed, onMounted } from 'vue'

import IconButton from '../components/IconButton.vue'
import PointPickerButton from '../components/PointPickerButton.vue'
import { NEW_OFFICE, useOffices } from '../composables/useOffices.js'

const {
  offices,
  loading,
  saving,
  errorMessage,
  errorDetails,
  noticeMessage,
  editingId,
  form,
  load,
  startCreate,
  startEdit,
  cancelEdit,
  saveForm,
  remove,
} = useOffices()

// на карте выбора видны остальные офисы — чтобы не поставить два в одну точку
const otherOffices = computed(() =>
  offices.value
    .filter((office) => office.id !== editingId.value)
    .map((office) => ({
      latitude: office.latitude,
      longitude: office.longitude,
      label: `Офис «${office.name}» · ${office.address}`,
    })),
)

function applyPickedPoint(latitude, longitude) {
  form.value.latitude = latitude
  form.value.longitude = longitude
}

onMounted(load)
</script>

<template>
  <div class="workspace">
    <header class="workspace-title">
      <h1>Офисы</h1>
      <p>Всего {{ offices.length }} · откуда бригады выезжают на смену</p>
    </header>

    <div v-if="errorMessage" class="message error">
      <strong>{{ errorMessage }}</strong>
      <ul v-if="errorDetails.length">
        <li v-for="(detail, index) in errorDetails" :key="index">{{ detail }}</li>
      </ul>
    </div>

    <p v-if="loading" class="muted">Загружаю справочники…</p>

    <template v-else>
      <section class="reference-block">
        <div class="list-bar">
          <button class="primary" :disabled="editingId !== null" @click="startCreate">+ Добавить офис</button>
        </div>

        <div class="table-scroll">
          <table class="data-table fixed-columns">
            <colgroup>
              <col style="width: 70px" />
              <col style="width: 200px" />
              <col />
              <col style="width: 180px" />
              <col style="width: 130px" />
              <col style="width: 110px" />
            </colgroup>
            <thead>
              <tr>
                <th>№</th>
                <th>Название</th>
                <th>Адрес</th>
                <th>Координаты</th>
                <th>Исполнителей</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <template v-for="office in [...offices, ...(editingId === NEW_OFFICE ? [null] : [])]" :key="office?.id ?? 'new'">
                <tr v-if="office === null || office.id === editingId" class="editing">
                  <td class="number-cell">{{ office?.id ?? '—' }}</td>
                  <td><input v-model="form.name" placeholder="Восток" aria-label="название офиса" /></td>
                  <td>
                    <input v-model="form.address" placeholder="г. Москва, ул …" aria-label="адрес офиса" />
                  </td>
                  <td>
                    <div class="coordinates-cell">
                      <div class="coordinate-inputs">
                        <input v-model="form.latitude" type="number" step="any" placeholder="широта" />
                        <input v-model="form.longitude" type="number" step="any" placeholder="долгота" />
                      </div>
                      <PointPickerButton
                        :title="`Где офис${form.name ? ` «${form.name}»` : ''}`"
                        hint="Указать точку на карте или ввести координаты"
                        :latitude="form.latitude"
                        :longitude="form.longitude"
                        :landmarks="otherOffices"
                        @pick="applyPickedPoint"
                      />
                    </div>
                  </td>
                  <td class="number-cell">{{ office?.engineer_count ?? 0 }}</td>
                  <td>
                    <div class="row-actions">
                      <IconButton
                        icon="save"
                        :label="saving ? 'Сохраняю…' : 'Сохранить'"
                        variant="primary"
                        :disabled="saving"
                        @click="saveForm"
                      />
                      <IconButton icon="cancel" label="Отмена" :disabled="saving" @click="cancelEdit" />
                    </div>
                  </td>
                </tr>

                <tr v-else>
                  <td class="number-cell">{{ office.id }}</td>
                  <td><strong>{{ office.name }}</strong></td>
                  <td>{{ office.address }}</td>
                  <td class="number-cell">{{ office.latitude.toFixed(6) }}, {{ office.longitude.toFixed(6) }}</td>
                  <td class="number-cell">{{ office.engineer_count }}</td>
                  <td>
                    <div class="row-actions">
                      <IconButton icon="edit" label="Изменить" :disabled="editingId !== null" @click="startEdit(office)" />
                      <IconButton
                        icon="delete"
                        label="Удалить"
                        variant="danger"
                        :disabled="editingId !== null || saving"
                        @click="remove(office)"
                      />
                    </div>
                  </td>
                </tr>
              </template>

              <tr v-if="!offices.length && editingId !== NEW_OFFICE">
                <td colspan="6" class="empty">Офисов нет — добавьте первый</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>

    <Transition name="toast">
      <div v-if="noticeMessage" class="toast" role="status">{{ noticeMessage }}</div>
    </Transition>
  </div>
</template>

<style scoped>
.reference-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
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
