// Стоит ли точка ровно в офисе. Отдельного переключателя «из офиса» в форме нет:
// бригада по умолчанию стоит в офисе, а сдвинули координаты — значит, своя точка.
// Совпадение до шестого знака — точность, с которой координаты хранятся в БД.

const EPSILON = 0.0000005

export function isAtOffice(latitude, longitude, office) {
  if (!office || latitude === '' || longitude === '' || latitude === null || longitude === null) return false
  return (
    Math.abs(Number(latitude) - office.latitude) < EPSILON && Math.abs(Number(longitude) - office.longitude) < EPSILON
  )
}
