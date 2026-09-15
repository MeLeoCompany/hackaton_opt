<script setup>
import { ref } from 'vue'

defineProps({
  busy: { type: Boolean, required: true },
})
const emit = defineEmits(['import', 'download-template'])

const fileInput = ref(null)
const selectedFile = ref(null)

function rememberFile(event) {
  selectedFile.value = event.target.files[0] ?? null
}

function upload() {
  if (!selectedFile.value) return
  emit('import', selectedFile.value)
  selectedFile.value = null
  fileInput.value.value = ''
}
</script>

<template>
  <section class="csv-import">
    <div class="controls">
      <input ref="fileInput" type="file" accept=".csv,text/csv" @change="rememberFile" />
      <button class="primary" :disabled="!selectedFile || busy" @click="upload">
        {{ busy ? 'Загружаю…' : 'Загрузить CSV' }}
      </button>
      <button :disabled="busy" @click="emit('download-template')">Скачать шаблон</button>
    </div>
    <p class="hint">
      Разделитель «;», кодировка UTF-8 или Windows-1251. Заявка с уже существующим номером
      обновится, без номера или с новым — добавится. Если в файле есть хоть одна ошибка,
      не загрузится ничего: список ошибок по строкам появится ниже.
    </p>
  </section>
</template>

<style scoped>
.csv-import {
  padding: 12px 14px;
  border: 1px dashed #cbd5e1;
  border-radius: 8px;
  background: #f8fafc;
}

.controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #64748b;
}
</style>
