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

// Keep the version-specific scene projection here. App code receives only pixel
// geometry and the existing legend actions, never a private renderer instance.
const pickingMarker = '      case "opentrading.indicatorPicking":'
const pickingBridge = `${pickingMarker}
        return {
          selected: () => this.inputsUI.selectedId,
          select: (id) => id ? this.inputsUI.selectRow(id) : this.inputsUI.clearSelection(),
          menu: (id, x, y) => this.inputsUI.openRowMenu(id, x, y),
          blocked: (x, y) => Boolean(this.userDrawings?.cursorAt(x, y)),
          geometry: (onlyId) => {
            const out = [], r = this.coords.visibleLogicalRange();
            const models = [...this.scene.indicators.values()].sort((a, b) => this.scene.zOf(a.id) - this.scene.zOf(b.id));
            for (const model of models) {
              if (model.legend === false || onlyId && model.id !== onlyId) continue;
              const home = this.scene.panes.get(model.paneId ?? PRICE_PANE_ID);
              if (!home || home.collapsed || home.bounds.height <= 0) continue;
              const offset = this.scene.offsetOf(model.id);
              for (const series of model.series) {
                if (!("points" in series) || !seriesShownOn(series, "pane")) continue;
                const pane = series.overlay ? this.scene.panes.get(PRICE_PANE_ID) : home;
                if (!pane || pane.collapsed || pane.bounds.height <= 0) continue;
                const scale = series.overlay ? pane.scale : this.scene.scaleFor(model, pane);
                const i0 = Math.max(0, Math.floor(r.from) - offset - 1);
                const i1 = Math.min(series.points.length - 1, Math.ceil(r.to) - offset + 1);
                const points = [];
                for (let i = i0; i <= i1; i++) {
                  const p = series.points[i];
                  const y = p && p.value != null ? this.coords.priceToY(p.value, scale, pane.bounds) : NaN;
                  points.push(Number.isFinite(y) ? { x: this.coords.logicalToX(i + offset), y, color: p.color ?? series.style.color } : null);
                }
                out.push({ id: model.id, kind: series.kind, points, width: series.style.width,
                  top: pane.bounds.top, bottom: pane.bounds.top + pane.bounds.height, right: this.coords.width,
                  halfWidth: columnHalfWidth(this.coords.bodySpacing()),
                  base: this.coords.priceToY(series.style.base ?? 0, scale, pane.bounds) });
              }
              if (model.native?.type === "volume" && this.volumeActive && !this.volumeHidden && this.scene.volumeLayer) {
                const i0 = Math.max(0, Math.floor(r.from)), i1 = Math.min(this.bars.length - 1, Math.ceil(r.to));
                let max = 0;
                for (let i = i0; i <= i1; i++) max = Math.max(max, this.bars[i].volume ?? 0);
                if (max <= 0) continue;
                const data = this.scene.volumeLayer, bottom = home.bounds.top + home.bounds.height;
                const height = home.bounds.height * (home.kind === "price" ? data.heightFrac : VOLUME_PANE_FILL_FRAC);
                const points = [];
                for (let i = i0; i <= i1; i++) {
                  const b = this.bars[i];
                  points.push({ x: this.coords.logicalToX(i), y: bottom - (b.volume ?? 0) / max * height,
                    color: b.close >= b.open ? data.upColor : data.downColor });
                }
                out.push({ id: model.id, kind: "columns", points, width: 1, top: home.bounds.top,
                  bottom, right: this.coords.width, base: bottom, halfWidth: columnHalfWidth(this.coords.bodySpacing()) });
              }
            }
            return out;
          }
        };
`

// All application entry points must use the same correction. Validate every
// target before writing so unexpected upstream bytes fail without partial edits.
const files = ['chunk-JSVCWYBF.js', 'index.cjs', 'widget.cjs', 'workspace.cjs']
const updates = []
for (const name of files) {
  const file = new URL('dist/' + name, root)
  const original = fs.readFileSync(file, 'utf8')
  let source = original
  if (source.includes(pickingMarker)) {
    const start = source.indexOf(pickingMarker), end = source.indexOf('      case "logScale":', start)
    if (end < 0) throw new Error(`Unexpected Vela indicator bridge boundary: ${name}`)
    source = source.slice(0, start) + pickingBridge + source.slice(end)
  } else {
    const marker = '  readFeature(key) {\n    switch (key) {\n'
    if (!source.includes(marker)) throw new Error(`Unexpected Vela renderer feature bridge: ${name}`)
    source = source.replace(marker, marker + pickingBridge)
  }
  // Migrate the first help hook, which ran after the dialog had captured stale inputs.
  source = source.replace(
    '    const tabDefs = tabInputs(row.inputs);\n    const help = { id: row.id, tabs: [] };\n    host.dispatchEvent(new CustomEvent("opentrading:indicator-settings", { bubbles: true, detail: help }));\n    tabDefs.push(...help.tabs);',
    '    const tabDefs = tabInputs(row.inputs);\n    tabDefs.push(...help.tabs);',
  )
  for (const [before, after] of [
    ['    this.openId = row.id;\n    this.snapshot = { ...row.values };', '    this.openId = row.id;\n    const help = { id: row.id, tabs: [], values: row.values, propValues: row.propValues };\n    this.host.container.dispatchEvent(new CustomEvent("opentrading:indicator-settings", { bubbles: true, detail: help }));\n    row.values = { ...help.values };\n    row.propValues = { ...help.propValues };\n    this.snapshot = { ...row.values };'],
    ['    const tabDefs = tabInputs(row.inputs);', '    const tabDefs = tabInputs(row.inputs);\n    tabDefs.push(...help.tabs);'],
    ['      bodies.push(this.buildTabBody(def.inputs, row, gates));', '      bodies.push(def.body ?? this.buildTabBody(def.inputs, row, gates));'],
    ['      if (def.inputs.every((d) => d.when)) {', '      if (def.inputs.length > 0 && def.inputs.every((d) => d.when)) {'],
    ['    this.rowMenuId = id;\n    const items = [{', '    this.rowMenuId = id;\n    const items = [{ id: "settings", label: "Settings\u2026" }, {'],
    ['          if (itemId !== "values" || !this.rowMenuId) return;', '          if (itemId === "settings" && this.rowMenuId) { this.openDialog(this.rowMenuId); return; }\n          if (itemId !== "values" || !this.rowMenuId) return;'],
  ]) {
    if (source.includes(after)) continue
    if (!source.includes(before)) throw new Error(`Unexpected Vela indicator menu: ${name}`)
    source = source.replace(before, after)
  }
  // Keep the menu chevron at the outer edge instead of reserving a second
  // full button column. Migrate the earlier wide gutter as well as upstream.
  source = source.replace(
    'var TOOLBAR_WIDTH = typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches ? 88 : 68;',
    'var TOOLBAR_WIDTH = 44;',
  )
  for (const [before, after] of [
    ['var TOOLBAR_WIDTH = 44;', 'var TOOLBAR_WIDTH = typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches ? 56 : 44;'],
    ['var TOOLBAR_COLLAPSED_WIDTH = 16;', 'var TOOLBAR_COLLAPSED_WIDTH = typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches ? 44 : 32;'],
  ]) {
    if(source.includes(after))continue
    if(!source.includes(before))throw new Error(`Unexpected Vela toolbar sizing: ${name}`)
    source=source.replace(before,after)
  }
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
