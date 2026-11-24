// Vela 0.7.6 strokes every plot segment separately. At fractional pixel
// positions, translucent joins acquire repeating antialiasing seams. Stroke
// each connected, same-color run once, preserving gaps and color changes.
import fs from 'node:fs'
import crypto from 'node:crypto'

const root = new URL('../node_modules/@luxalgo/vela/', import.meta.url)
const meta = JSON.parse(fs.readFileSync(new URL('package.json', root), 'utf8'))
if (meta.version !== '0.7.6') throw new Error('Revalidate Vela polyline correction before upgrading')

const signature = '  drawPolyline(ctx, s, pane, coords, i0, i1, step, off = 0) {'
const expected = '4a25c0179b6444967369c25acc7c0e00a5453b493ea25d763349d08cc7b067af'
const replacement = `${signature}
    // OpenTrading: connected same-color plots share one antialiased stroke.
    ctx.save();
    ctx.lineWidth = Math.max(1, s.style.width);
    ctx.lineJoin = "round";
    ctx.lineCap = "butt";
    setDash(ctx, s.style.lineStyle);
    let have = false;
    let color;
    let startX = 0, startY = 0, lastX = 0, lastY = 0;
    let pending = false;
    // Redundant collinear vertices also trigger Chromium's thin-stroke
    // antialiasing artifacts. Keep the identical geometry with fewer vertices.
    const lineTo = (x, y) => {
      if (pending) {
        const ax = lastX - startX, ay = lastY - startY;
        const bx = x - lastX, by = y - lastY;
        if (Math.abs(ax * by - ay * bx) > 1e-8 || ax * bx + ay * by < 0) {
          ctx.lineTo(lastX, lastY);
          startX = lastX;
          startY = lastY;
        }
      }
      lastX = x;
      lastY = y;
      pending = true;
    };
    const flush = () => {
      if (have) {
        if (pending) ctx.lineTo(lastX, lastY);
        ctx.stroke();
      }
      have = false;
      pending = false;
    };
    for (let i = Math.max(1, i0 - 1); i <= i1; i += 1) {
      const p = s.points[i - off];
      const pv = s.points[i - 1 - off];
      if (!p || p.value === null || !pv || pv.value === null) {
        flush();
        continue;
      }
      const x = coords.logicalToX(i);
      const y = coords.priceToY(p.value, pane.scale, pane.bounds);
      const nextColor = p.color ?? s.style.color;
      if (!have || color !== nextColor) {
        flush();
        color = nextColor;
        ctx.strokeStyle = color;
        ctx.beginPath();
        startX = coords.logicalToX(i - 1);
        startY = coords.priceToY(pv.value, pane.scale, pane.bounds);
        ctx.moveTo(startX, startY);
      }
      if (step) lineTo(x, coords.priceToY(pv.value, pane.scale, pane.bounds));
      lineTo(x, y);
      have = true;
    }
    flush();
    ctx.restore();
  }`

const glSignature = '  emitPolyline(b, s, pane, coords, i0, i1, step, off = 0) {'
const glExpected = '397d84728223d565fd8026257d215b31fb99ef9662c43690c7c96acfe7361d31'
const glReplacement = `${glSignature}
    // OpenTrading: adjacent solid segments share mesh edges. Round circles at
    // every vertex overpaint translucent segments and appear as bright dots.
    const w = Math.max(1, s.style.width);
    const hw = w / 2;
    const pattern = DASH[s.style.lineStyle] ?? null;
    if (pattern || step) {
      for (let i = Math.max(1, i0 - 1); i <= i1; i += 1) {
        const p = s.points[i - off], pv = s.points[i - 1 - off];
        if (!p || p.value === null || !pv || pv.value === null) continue;
        const x = coords.logicalToX(i), y = coords.priceToY(p.value, pane.scale, pane.bounds);
        const px = coords.logicalToX(i - 1), py = coords.priceToY(pv.value, pane.scale, pane.bounds);
        const c = parseColor(p.color ?? s.style.color);
        if (step) {
          b.dashedSeg(px, py, x, py, w, c, pattern);
          b.dashedSeg(x, py, x, y, w, c, pattern);
        } else b.dashedSeg(px, py, x, y, w, c, pattern);
      }
      return;
    }
    let run = [];
    const flush = () => {
      if (run.length < 2) { run = []; return; }
      const normals = [];
      for (let i = 1; i < run.length; i += 1) {
        const dx = run[i].x - run[i - 1].x, dy = run[i].y - run[i - 1].y;
        const length = Math.hypot(dx, dy) || 1;
        normals.push({ x: -dy / length, y: dx / length });
      }
      const edges = run.map((p, i) => {
        const a = normals[Math.max(0, i - 1)], z = normals[Math.min(i, normals.length - 1)];
        const mx = a.x + z.x, my = a.y + z.y;
        const denominator = mx * z.x + my * z.y;
        const factor = denominator > 1e-6 ? Math.min(hw / denominator, 4 * hw / Math.hypot(mx, my)) : 0;
        const nx = factor ? mx * factor : z.x * hw, ny = factor ? my * factor : z.y * hw;
        return { lx: p.x + nx, ly: p.y + ny, rx: p.x - nx, ry: p.y - ny };
      });
      for (let i = 1; i < run.length; i += 1) {
        const a = edges[i - 1], z = edges[i];
        b.quad(a.lx, a.ly, z.lx, z.ly, z.rx, z.ry, a.rx, a.ry, parseColor(run[i].color));
      }
      run = [];
    };
    for (let i = Math.max(1, i0 - 1); i <= i1; i += 1) {
      const p = s.points[i - off], pv = s.points[i - 1 - off];
      if (!p || p.value === null || !pv || pv.value === null) { flush(); continue; }
      if (!run.length) run.push({ x: coords.logicalToX(i - 1), y: coords.priceToY(pv.value, pane.scale, pane.bounds), color: pv.color ?? s.style.color });
      run.push({ x: coords.logicalToX(i), y: coords.priceToY(p.value, pane.scale, pane.bounds), color: p.color ?? s.style.color });
    }
    flush();
  }`

// All application entry points must use the same correction. Validate every
// target before writing so unexpected upstream bytes fail without partial edits.
const files = ['chunk-JSVCWYBF.js', 'index.cjs', 'widget.cjs', 'workspace.cjs']
const updates = []
for (const name of files) {
  const file = new URL('dist/' + name, root)
  const original = fs.readFileSync(file, 'utf8')
  let source = original
  for (const [startMarker, endMarker, hash, corrected] of [
    [signature, '\n  drawArea(', expected, replacement],
    [glSignature, '\n  emitArea(', glExpected, glReplacement],
  ]) {
    const start = source.indexOf(startMarker), end = source.indexOf(endMarker, start)
    if (start < 0 || end < 0 || source.indexOf(startMarker, start + 1) >= 0) throw new Error(`Unexpected Vela polyline method: ${name}`)
    const method = source.slice(start, end)
    if (method === corrected) continue
    if (crypto.createHash('sha256').update(method).digest('hex') !== hash) throw new Error(`Unexpected upstream Vela polyline bytes: ${name}`)
    source = source.slice(0, start) + corrected + source.slice(end)
  }
  if (source !== original) updates.push({ file, source, name })
}
for (const { file, source, name } of updates) {
  fs.writeFileSync(file, source)
  console.log('Applied Vela continuous-polyline correction:', name)
}
