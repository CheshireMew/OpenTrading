// Shared by Tailwind, application surfaces and canvas-rendered charts.
export const DARK_PALETTE = Object.freeze({
  canvas: '#151619',
  panel: '#1b1d23',
  toolbar: '#15181e',
  elevated: '#22252d',
  hover: '#292c34',
  border: '#2a2b30',
  borderStrong: '#434651',
  grid: '#24262d',
  text: '#d1d4dc',
  title: '#f0f3fa',
  muted: '#959ca9',
  faint: '#787f8d',
  accent: '#22ab94',
  accentHover: '#1c9580',
  positive: '#089981',
  negative: '#f23645',
  blue: '#5086f5',
})

export const DARK_CHART_COLORS = Object.freeze({
  bg: DARK_PALETTE.canvas,
  grid: DARK_PALETTE.grid,
  text: DARK_PALETTE.muted,
  upColor: DARK_PALETTE.positive,
  downColor: DARK_PALETTE.negative,
})

export const DARK_NEUTRALS = Object.freeze({
  50: DARK_PALETTE.title,
  100: '#e3e6ed',
  200: DARK_PALETTE.text,
  300: '#b2b8c4',
  400: DARK_PALETTE.muted,
  500: DARK_PALETTE.faint,
  600: DARK_PALETTE.borderStrong,
  700: DARK_PALETTE.border,
  800: DARK_PALETTE.panel,
  900: DARK_PALETTE.canvas,
  950: '#101114',
})

export const hexRgb = (hex) => hex.slice(1).match(/.{2}/g).map((value) => parseInt(value, 16)).join(' ')
