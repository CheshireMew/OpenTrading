// Shared by Tailwind, application surfaces and canvas-rendered charts.
export const LIGHT_PALETTE = Object.freeze({
  canvas: '#f7f4ed',
  panel: '#ffffff',
  toolbar: '#fbfaf7',
  elevated: '#f1eee7',
  hover: '#eae7df',
  border: '#e4ded3',
  borderStrong: '#b8b2a8',
  grid: '#ece8df',
  text: '#383b36',
  title: '#18251f',
  muted: '#65645d',
  faint: '#746e65',
  accent: '#0f6b4f',
  accentHover: '#0b5a41',
  positive: '#087e68',
  negative: '#c52d3c',
  blue: '#2868c8',
})

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
  faint: '#8992a2',
  accent: '#22ab94',
  accentHover: '#1c9580',
  positive: '#089981',
  negative: '#f23645',
  blue: '#5086f5',
})

export const LIGHT_NEUTRALS = Object.freeze({
  50: LIGHT_PALETTE.toolbar,
  100: LIGHT_PALETTE.elevated,
  200: LIGHT_PALETTE.border,
  300: '#cdc7bd',
  400: '#918b81',
  500: LIGHT_PALETTE.faint,
  600: LIGHT_PALETTE.muted,
  700: '#4b4c45',
  800: LIGHT_PALETTE.text,
  900: '#242c26',
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
