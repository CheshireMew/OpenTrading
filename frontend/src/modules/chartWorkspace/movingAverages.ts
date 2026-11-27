import { getNativeIndicator, registerNativeIndicator } from '@luxalgo/vela/plugin'
import type { InputValue, NativeIndicator, NativeIndicatorContext, NativeIndicatorDescriptor, NativeIndicatorOutput } from '@luxalgo/vela'

export const MA_LINES_KEY = 'additionalLines'
export const MA_SOURCES = ['Close', 'Open', 'High', 'Low', 'HL2', 'HLC3', 'OHLC4', 'HLCC4'] as const
export const MA_COLORS = ['#3786ff', '#f5a623', '#9b6dff', '#089981', '#e85d75', '#26c6da']
export type MovingAverageLine = { id: string; length: number; source: string; offset: number; color: string }
type Inputs = Record<string, InputValue>
const integer = (value: unknown, fallback: number, min: number, max: number) =>
  typeof value === 'number' && Number.isFinite(value) ? Math.max(min, Math.min(max, Math.trunc(value))) : fallback

export function movingAverageLines(inputs: Inputs): MovingAverageLine[] {
  const source = MA_SOURCES.includes(inputs.source as typeof MA_SOURCES[number]) ? String(inputs.source) : 'Close'
  const read = (line: Record<string, unknown>, id: string): MovingAverageLine => ({
    id, length: integer(line.length, 20, 1, 5000), offset: integer(line.offset, 0, -500, 500),
    source,
    color: typeof line.color === 'string' && /^#[\da-f]{6}$/i.test(line.color) ? line.color : MA_COLORS[0]!,
  })
  // The first line keeps the original input keys, so existing layouts and scripts
  // setting length/source/offset/color retain their meaning.
  const lines = [read(inputs, 'primary')], ids = new Set(['primary'])
  try {
    const extra: unknown = JSON.parse(String(inputs[MA_LINES_KEY] ?? '[]'))
    if (Array.isArray(extra)) for (const [index, line] of extra.entries()) {
      if (!line || typeof line !== 'object' || Array.isArray(line)) continue
      let id = typeof line.id === 'string' && line.id ? line.id : `line-${index}`
      while (ids.has(id)) id += '-copy'
      ids.add(id); lines.push(read(line, id))
    }
  } catch { /* A legacy single-line indicator has no additional-line payload. */ }
  return lines
}

const extended = new WeakSet<NativeIndicatorDescriptor>()
export function registerMovingAverageDefinitions() {
  for (const type of ['sma', 'ema']) {
    const original = getNativeIndicator(type)
    if (!original || extended.has(original)) continue
    const label = type === 'sma' ? 'MA' : 'EMA'
    const descriptor: NativeIndicatorDescriptor = {
      ...original,
      inputsSchema: () => [...original.inputsSchema(), { key: MA_LINES_KEY, title: 'Additional lines', type: 'string', defval: '[]' }],
      defaultInputs: () => ({ ...original.defaultInputs(), [MA_LINES_KEY]: '[]' }),
      create() {
        let context: NativeIndicatorContext | undefined, inputs: Inputs = {}, batching = false, suspended = false
        const children = new Map<string, { line: MovingAverageLine; instance: NativeIndicator; output: NativeIndicatorOutput }>()
        const publish = () => {
          if (!context || batching || suspended) return
          context.emit({ series: [...children.values()].flatMap(({ line, output }) => (output.series ?? []).map(series => ({
            ...series, id: `${series.id}:${line.id}`, title: `${label} ${line.length}`,
          }))) })
        }
        const batch = (run: () => void) => { batching = true; try { run() } finally { batching = false; publish() } }
        const configure = () => {
          if (!context) return
          batch(() => {
            const lines = movingAverageLines(inputs), keep = new Set(lines.map(line => line.id))
            for (const [id, child] of children) if (!keep.has(id)) { child.instance.stop(); children.delete(id) }
            for (const line of lines) {
              const values = { length: line.length, source: line.source, offset: line.offset, color: line.color }
              const previous = children.get(line.id)
              if (previous) {
                if (JSON.stringify(previous.line) === JSON.stringify(line)) continue
                previous.line = line; previous.instance.setInputs(values)
              } else {
                const child = { line, instance: original.create(), output: {} as NativeIndicatorOutput }
                children.set(line.id, child)
                child.instance.start({ ...context!, emit(output) { child.output = output; publish() } }, values)
                if (suspended) child.instance.suspend()
              }
            }
          })
        }
        return {
          start(ctx, values) { context = ctx; suspended = false; inputs = { ...original.defaultInputs(), ...values }; configure() },
          setInputs(values) { inputs = { ...inputs, ...values }; configure() },
          onBars() { batch(() => { for (const child of children.values()) child.instance.onBars() }) },
          onViewport(range) { batch(() => { for (const child of children.values()) child.instance.onViewport(range) }) },
          suspend() { suspended = true; for (const child of children.values()) child.instance.suspend() },
          resume() { suspended = false; batch(() => { for (const child of children.values()) child.instance.resume() }) },
          stop() { context = undefined; for (const child of children.values()) child.instance.stop(); children.clear() },
        }
      },
    }
    extended.add(descriptor); registerNativeIndicator(descriptor)
  }
}
