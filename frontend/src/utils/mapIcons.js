// Значки карты плана — рисунками SVG (эмодзи есть не во всех шрифтах): бригада по её
// транспорту и способ передвижения на участке пути общественным транспортом.

const svg = (body, size = 16) =>
  `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" stroke="currentColor" ` +
  `stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`

const VAN = '<path d="M14 17V6H3v11h2M9 17h6M14 9h4l3 4v4h-2"/><circle cx="7" cy="17" r="2"/><circle cx="17" cy="17" r="2"/>'
const WALKER =
  '<circle cx="13" cy="4" r="2"/><path d="M9 21l3-7 3 3v4M7 12l3-4 4 1 2 3 3 1M11 8l-1 5"/>'
const BICYCLE =
  '<circle cx="5.5" cy="17" r="3.5"/><circle cx="18.5" cy="17" r="3.5"/><path d="M5.5 17l4-7h6l3 7M9.5 10l3 7M14 6h2l-.5 4"/>'
const BUS =
  '<rect x="4" y="3" width="16" height="15" rx="3"/><path d="M4 11h16M8 18v3M16 18v3"/><circle cx="8" cy="14.5" r=".6"/><circle cx="16" cy="14.5" r=".6"/>'
const TRAM =
  '<rect x="5" y="5" width="14" height="13" rx="2"/><path d="M5 11h14M9 2h6M12 2v3M8 18l-2 4M16 18l2 4"/>'
const METRO = '<path d="M4 19V6l8 9 8-9v13"/>'
const FERRY = '<path d="M3 17c2 2 4 2 6 0s4-2 6 0 4 2 6 0M5 14l1-5h12l1 5M9 9V5h6v4"/>'

// значок бригады — по её транспорту (transport_id из справочника)
export const TRANSPORT_ICONS = { 1: VAN, 2: WALKER, 3: BICYCLE, 4: BUS }

// значок участка пути — по способу передвижения (mode из маршрутизатора)
export const MODE_ICONS = {
  walk: WALKER,
  bike: BICYCLE,
  bus: BUS,
  tram: TRAM,
  rail: TRAM,
  metro: METRO,
  ferry: FERRY,
  transit: BUS,
}

export function transportSvg(transportId, size) {
  return svg(TRANSPORT_ICONS[transportId] ?? VAN, size)
}

export function modeSvg(mode, size) {
  return svg(MODE_ICONS[mode] ?? BUS, size)
}
