// Параметры расчёта: что настраивается у cuOpt и как это объяснить оператору.
// У решателя настраивается только время поиска — оно же «точность»: чем дольше ищет,
// тем лучше маршруты. Остальное — вес пробега и сверка плана ОТ с расписанием.

export const SOLVER_FIELDS = [
  {
    key: 'time_limit_seconds',
    label: 'Время поиска, с',
    hint: 'Минимум времени на решение. Чем больше, тем лучше маршруты: у cuOpt это и есть точность',
    step: 0.5,
    min: 0.1,
  },
  {
    key: 'seconds_per_location',
    label: 'Добавка на точку, с',
    hint: 'Сколько секунд добавлять за каждую точку сверх бесплатных: большой день ищется дольше',
    step: 0.05,
    min: 0,
  },
  {
    key: 'free_locations',
    label: 'Точек без добавки',
    hint: 'До этого числа точек время поиска не растёт',
    step: 1,
    min: 0,
  },
  {
    key: 'max_time_limit_seconds',
    label: 'Максимум времени, с',
    hint: 'Выше этого лимита поиск не поднимается, каким бы большим ни был день',
    step: 5,
    min: 1,
  },
  {
    key: 'distance_weight',
    label: 'Вес пробега',
    hint: 'Насколько сильно пробег влияет на выбор между равными планами',
    step: 0.5,
    min: 0.1,
  },
  {
    key: 'equipment_reserve',
    label: 'Запас оборудования, шт',
    hint: 'Сколько штук выдавать бригаде сверх того, что нужно её заявкам по плану — на замену брака и новые заявки',
    step: 1,
    min: 0,
  },
  {
    key: 'transit_attempts',
    label: 'Попыток по расписанию',
    hint: 'Сколько раз пересчитывать план общественного транспорта по фактическому расписанию R5',
    step: 1,
    min: 1,
  },
]

// строки таблицы параметров: числовые поля и подробный лог решателя
export const SOLVER_ROWS = [
  ...SOLVER_FIELDS,
  {
    key: 'verbose_log',
    label: 'Подробный лог решателя',
    hint: 'cuOpt будет писать в журнал расчёта свой разбор — нужен, когда выясняют, почему план именно такой',
  },
]

// значение строки словами: у переключателя — «включён» / «выключен»
export function paramText(key, value) {
  if (key === 'verbose_log') return value ? 'включён' : 'выключен'
  return `${value}`
}

// подсказка под таблицей: сколько на самом деле будет искаться день
export function limitHint(params) {
  const numbers = numericParams(params)
  // смотрим только то, из чего складывается время: запас оборудования на него не влияет
  const timing = ['time_limit_seconds', 'seconds_per_location', 'free_locations', 'max_time_limit_seconds']
  if (timing.some((key) => Number.isNaN(numbers[key]))) return ''
  return `День из 20 точек будет искаться ${limitFor(numbers, 20)} с, из 200 точек — ${limitFor(numbers, 200)} с`
}

// сколько cuOpt будет искать решение для дня такого размера — показываем прямо в форме
export function limitFor(params, locations) {
  const adaptive = Math.max(locations - params.free_locations, 0) * params.seconds_per_location
  return Math.min(Math.max(params.time_limit_seconds, adaptive), params.max_time_limit_seconds)
}

// в форме значения живут строками — приводим к числам перед отправкой
export function numericParams(params) {
  const result = { verbose_log: Boolean(params.verbose_log) }
  for (const field of SOLVER_FIELDS) result[field.key] = Number(params[field.key])
  return result
}
