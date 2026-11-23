// Shared by Tailwind, application surfaces and canvas-rendered charts.
export const LIGHT_PALETTE = Object.freeze({
  canvas: '#f5f5f5',
  panel: '#ffffff',
  toolbar: '#ffffff',
  elevated: '#f0f0f0',
  hover: '#e8e8e8',
  border: '#dddddd',
  borderStrong: '#b5b5b5',
  grid: '#ededed',
  text: '#303030',
  title: '#131313',
  muted: '#626262',
  faint: '#767676',
  accent: '#181818',
  accentHover: '#333333',
  onAccent: '#ffffff',
  positive: '#089981',
  negative: '#f23645',
  blue: '#2962ff',
})

export const DARK_PALETTE = Object.freeze({
  canvas: '#0c0c0c',
  panel: '#151515',
  toolbar: '#171717',
  elevated: '#242424',
  hover: '#2c2c2c',
  border: '#333333',
  borderStrong: '#505050',
  grid: '#242424',
  text: '#d1d1d1',
  title: '#f2f2f2',
  muted: '#aaaaaa',
  faint: '#8b8b8b',
  accent: '#eeeeee',
  accentHover: '#ffffff',
  onAccent: '#151515',
  positive: '#089981',
  negative: '#f23645',
  blue: '#5086f5',
})

export const LIGHT_NEUTRALS = Object.freeze({
  50: LIGHT_PALETTE.toolbar,
  100: LIGHT_PALETTE.elevated,
  200: LIGHT_PALETTE.border,
  300: '#cccccc',
  400: '#999999',
  500: LIGHT_PALETTE.faint,
  600: LIGHT_PALETTE.muted,
  700: '#484848',
  800: LIGHT_PALETTE.text,
  900: '#242424',
  950: LIGHT_PALETTE.title,
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
  100: '#e3e3e3',
  200: DARK_PALETTE.text,
  300: '#bbbbbb',
  400: DARK_PALETTE.muted,
  500: DARK_PALETTE.faint,
  600: DARK_PALETTE.borderStrong,
  700: DARK_PALETTE.border,
  800: DARK_PALETTE.panel,
  900: DARK_PALETTE.canvas,
  950: '#080808',
})

export const hexRgb = (hex) => hex.slice(1).match(/.{2}/g).map((value) => parseInt(value, 16)).join(' ')
