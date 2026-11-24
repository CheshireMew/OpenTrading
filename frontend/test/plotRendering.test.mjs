import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'

const signature = '  drawPolyline(ctx, s, pane, coords, i0, i1, step, off = 0) {'
function methodFrom(name, startMarker = signature, endMarker = '\n  drawArea(') {
  const source = fs.readFileSync(new URL('../node_modules/@luxalgo/vela/dist/' + name, import.meta.url), 'utf8')
  const start = source.indexOf(startMarker), end = source.indexOf(endMarker, start)
  assert.ok(start >= 0 && end > start)
  return source.slice(start, end)
}
const method = methodFrom('chunk-JSVCWYBF.js')
const draw = new Function('setDash', 'return ({' + method + '}).drawPolyline')((ctx, style) => ctx.setLineDash(style === 'dashed' ? [6, 4] : style === 'dotted' ? [2, 3] : []))
const pane = { scale: {}, bounds: {} }
const coords = { logicalToX: index => index * 14.3 + 0.4, priceToY: value => value * 2 }
function paint(points, { step = false, off = 0, from = 0, to = points.length - 1, lineStyle = 'solid' } = {}) {
  const strokes = []
  let path, saved
  const ctx = {
    lineWidth: 7, lineCap: 'square', lineJoin: 'bevel', strokeStyle: 'original', dash: [1, 2],
    save() { saved = { lineWidth: this.lineWidth, lineCap: this.lineCap, lineJoin: this.lineJoin, strokeStyle: this.strokeStyle, dash: this.dash } },
    restore() { Object.assign(this, saved) },
    setLineDash(dash) { this.dash = dash },
    beginPath() { path = [] },
    moveTo(x, y) { path.push(['move', x, y]) },
    lineTo(x, y) { path.push(['line', x, y]) },
    stroke() { strokes.push({ color: this.strokeStyle, width: this.lineWidth, cap: this.lineCap, join: this.lineJoin, dash: this.dash, path: [...path] }) },
  }
  draw(ctx, { points, style: { color: 'rgba(163,230,53,0.2)', width: 2, lineStyle } }, pane, coords, from, to, step, off)
  assert.equal(ctx.lineWidth, 7)
  assert.equal(ctx.strokeStyle, 'original')
  assert.equal(ctx.lineCap, 'square')
  assert.deepEqual(ctx.dash, [1, 2])
  return strokes
}
const points = values => values.map((value, index) => typeof value === 'object' && value !== null ? { time: index, ...value } : { time: index, value })

test('translucent EMA joins use one stroke without changing width, alpha or values', () => {
  const data = points([30, 29, 29, 27, 26])
  const original = structuredClone(data)
  const strokes = paint(data)
  assert.equal(strokes.length, 1)
  assert.equal(strokes[0].color, 'rgba(163,230,53,0.2)')
  assert.equal(strokes[0].width, 2)
  assert.equal(strokes[0].path.length, data.length)
  assert.equal(strokes[0].join, 'round')
  assert.equal(strokes[0].cap, 'butt')
  assert.deepEqual(data, original)
})

test('missing plot values break the path and never connect across a gap', () => {
  const strokes = paint(points([1, 2, null, 8, 9, 10]))
  assert.equal(strokes.length, 2)
  assert.deepEqual(strokes.map(stroke => stroke.path.map(point => point[2])), [[2, 4], [16, 20]])
  assert.equal(paint(points([null, 1, null, 2])).length, 0)
})

test('per-bar colors still apply to their original segments', () => {
  const strokes = paint(points([1, 2, { value: 3, color: 'red' }, { value: 4, color: 'red' }, 5]))
  assert.deepEqual(strokes.map(stroke => stroke.color), ['rgba(163,230,53,0.2)', 'red', 'rgba(163,230,53,0.2)'])
  assert.deepEqual(strokes[1].path.map(point => point[2]), [4, 8])
})

test('step plots, dashed styles, visible boundaries and anchored offsets stay aligned', () => {
  const strokes = paint(points([10, 20, 30, 40]), { step: true, off: 5, from: 7, to: 8, lineStyle: 'dashed' })
  assert.equal(strokes.length, 1)
  assert.deepEqual(strokes[0].dash, [6, 4])
  assert.deepEqual(strokes[0].path, [
    ['move', coords.logicalToX(5), 20],
    ['line', coords.logicalToX(6), 20], ['line', coords.logicalToX(6), 40],
    ['line', coords.logicalToX(7), 40], ['line', coords.logicalToX(7), 60],
    ['line', coords.logicalToX(8), 60], ['line', coords.logicalToX(8), 80],
  ])
})

test('browser and Node renderer entry points share the pinned correction', () => {
  for (const name of ['index.cjs', 'widget.cjs', 'workspace.cjs']) assert.equal(methodFrom(name), method)
})

const glMethod = methodFrom('chunk-JSVCWYBF.js', '  emitPolyline(b, s, pane, coords, i0, i1, step, off = 0) {', '\n  emitArea(')
const emit = new Function('parseColor', 'DASH', 'return ({' + glMethod + '}).emitPolyline')(color => color, { dashed: [6, 4], dotted: [2, 3] })
function mesh(values) {
  const quads = []
  const builder = {
    quad(...args) { quads.push({ vertices: args.slice(0, 8), color: args[8] }) },
    circle() { assert.fail('Solid EMA vertices must not overpaint a circular marker') },
    dashedSeg() { assert.fail('Solid EMA segments must share mesh edges') },
  }
  const data = points(values)
  emit(builder, { points: data, style: { color: 'rgba(163,230,53,0.2)', width: 2, lineStyle: 'solid' } }, pane, coords, 0, data.length - 1, false)
  return quads
}

test('hardware-accelerated EMA segments share identical edges without circular overdraw', () => {
  const quads = mesh([30, 29, 28, 31])
  assert.equal(quads.length, 3)
  for (let index = 1; index < quads.length; index++) {
    const previous = quads[index - 1].vertices, current = quads[index].vertices
    assert.deepEqual(previous.slice(2, 4), current.slice(0, 2))
    assert.deepEqual(previous.slice(4, 6), current.slice(6, 8))
  }
  for (const quad of quads) assert.equal(quad.color, 'rgba(163,230,53,0.2)')
})

test('hardware-accelerated plots preserve gaps, colors and bounded joins at sharp turns', () => {
  const quads = mesh([30, { value: 28, color: 'red' }, null, 30, 10000, 10])
  assert.equal(quads.length, 3)
  assert.deepEqual(quads.map(quad => quad.color), ['red', 'rgba(163,230,53,0.2)', 'rgba(163,230,53,0.2)'])
  for (const quad of quads) assert.ok(quad.vertices.every(Number.isFinite))
  const joint = quads[1].vertices.slice(2, 4)
  assert.ok(Math.hypot(joint[0] - coords.logicalToX(4), joint[1] - 20000) <= 4.00001)
  for (const name of ['index.cjs', 'widget.cjs', 'workspace.cjs']) assert.equal(methodFrom(name, '  emitPolyline(b, s, pane, coords, i0, i1, step, off = 0) {', '\n  emitArea('), glMethod)
})
