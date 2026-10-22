export const DARK_PALETTE: Readonly<Record<
  'canvas' | 'panel' | 'toolbar' | 'elevated' | 'hover' | 'border' | 'borderStrong' |
  'grid' | 'text' | 'title' | 'muted' | 'faint' | 'accent' | 'accentHover' |
  'positive' | 'negative' | 'blue', string
>>
export const DARK_CHART_COLORS: Readonly<Record<'bg' | 'grid' | 'text' | 'upColor' | 'downColor', string>>
export const DARK_NEUTRALS: Readonly<Record<number, string>>
export function hexRgb(hex: string): string
