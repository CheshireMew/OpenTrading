import { getNativeIndicator, registerNativeIndicator } from '@luxalgo/vela/plugin'
import type { InputSchema, InputValue, NativeIndicatorDescriptor, PriceLine } from '@luxalgo/vela'

const ADX_TYPE = 'average-directional-index'
const levels: InputSchema[] = [
  { key: 'showUpperLevel', title: 'Show upper level', type: 'bool', defval: false, tab: 'Reference lines' },
  { key: 'upperLevel', title: 'Upper level', type: 'float', defval: 30, min: 0, max: 100, step: 1,
    tab: 'Reference lines', when: { key: 'showUpperLevel', equals: true } },
  { key: 'showLowerLevel', title: 'Show lower level', type: 'bool', defval: false, tab: 'Reference lines' },
  { key: 'lowerLevel', title: 'Lower level', type: 'float', defval: 10, min: 0, max: 100, step: 1,
    tab: 'Reference lines', when: { key: 'showLowerLevel', equals: true } },
]
const extended = new WeakSet<NativeIndicatorDescriptor>()

export function registerWorkspaceIndicatorDefinitions() {
  const original = getNativeIndicator(ADX_TYPE)
  if (!original || extended.has(original)) return
  const descriptor: NativeIndicatorDescriptor = {
    ...original,
    inputsSchema: () => [...original.inputsSchema(), ...levels],
    defaultInputs: () => ({ ...original.defaultInputs(), ...Object.fromEntries(levels.map(input => [input.key, input.defval])) }),
    create() {
      const instance = original.create()
      let values: Record<string, InputValue> = {}
      return {
        start(ctx, inputs) {
          values = { ...inputs }
          instance.start({ ...ctx, emit(output) {
            const priceLines: PriceLine[] = []
            for (const [show, level, title] of [
              ['showUpperLevel', 'upperLevel', 'Upper level'], ['showLowerLevel', 'lowerLevel', 'Lower level'],
            ]) {
              const price = Number(values[level])
              if (values[show] === true && Number.isFinite(price)) priceLines.push({
                id: `${ctx.id}:${level}`, paneId: '', price, title: `${title} ${price}`,
                color: '#8a8d98', lineStyle: 'dashed', width: 1,
              })
            }
            // Replace the library's fixed 25 line with the user's optional levels.
            ctx.emit({ ...output, priceLines })
          } }, inputs)
        },
        setInputs(inputs) { values = { ...values, ...inputs }; instance.setInputs(inputs) },
        onBars: () => instance.onBars(), onViewport: range => instance.onViewport(range),
        suspend: () => instance.suspend(), resume: () => instance.resume(), stop: () => instance.stop(),
      }
    },
  }
  extended.add(descriptor)
  registerNativeIndicator(descriptor)
}
