import assert from 'node:assert/strict'
import test from 'node:test'
import { mkdir, writeFile } from 'node:fs/promises'
import { browserSession } from './helpers/browserSession.mjs'

test('workspace panels, layout links, settings and themes stay consistent across active charts', {
  timeout: 60_000, skip: process.env.OPENTRADING_TEST_COLLECT === '1' || !process.env.OPENTRADING_TEST_BROWSER,
}, async () => {
  const session = await browserSession({ publicSite: false })
  const page = await session.page(await session.context())
  try {
    await page.viewport(1440, 900)
    const initial = await page.evaluate(`
      const { createApp, nextTick, createRouter, createMemoryHistory } = await import('/test/helpers/vuePage.ts');
      const i18n = (await import('/src/i18n/index.ts')).default; i18n.global.locale.value = 'zh-CN';
      window.theme = (await import('/src/composables/useTheme.ts')).useTheme().theme; theme.value = 'dark';
      await import('/src/style.css');
      const { chartApi } = await import('/src/modules/chartWorkspace/api.ts');
      window.catalog = ['BTC', 'ETH'].map((coin, index) => ({
        id: 'binance:spot:' + coin + 'USDT', symbol: coin + 'USDT', name: coin + '/USDT', exchange: 'binance', market: 'spot',
        currency: 'USDT', timezone: 'Etc/UTC', session: '24x7', metadata: { mintick: 0.01, basecurrency: coin },
        timeframes: ['1m','5m','15m','30m','1h','4h','1d','1w','1M'],
      }));
      chartApi.symbols = async () => catalog;
      chartApi.documents = async kind => kind === 'watchlists' ? [{ id: 'default', version: 1, name: '我的自选', data: { symbols: catalog.map(s => s.id) } }] : [];
      chartApi.save = async (kind, id, body) => ({ id, version: (body.expected_version ?? 0) + 1, name: body.name, data: body.data });
      chartApi.quotes = async ids => ids.map(id => ({ id, price: id.includes('ETH') ? 205 : 105, change: 1, change_pct: 1, updated_at: new Date().toISOString() }));
      chartApi.bars = async query => {
        const step = { '1m':60000, '5m':300000, '15m':900000, '30m':1800000, '1h':3600000, '4h':14400000, '1d':86400000, '1w':604800000, '1M':2592000000 }[query.timeframe];
        const end = Math.floor(Number(query.end ?? Date.now()) / step) * step, count = Number(query.limit ?? 1000), base = query.symbol.includes('ETH') ? 200 : 100;
        return { symbol: catalog.find(s => s.id === query.symbol), timeframe: query.timeframe, source: 'fixture',
          bars: Array.from({ length: count }, (_, index) => ({ time: end - (count - index) * step, closeTime: end - (count - index - 1) * step,
            open: base + index % 10, high: base + 12, low: base - 2, close: base + 1 + index % 10, volume: 20, closed: true })) };
      };
      window.errors = []; window.addEventListener('error', event => errors.push(event.message));
      document.querySelector('#app').style.cssText = 'height:100dvh;width:100vw';
      const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] });
      await router.push('/'); await router.isReady();
      window.app = createApp((await import('/src/views/ChartWorkspace.vue')).default).use(i18n).use(router);
      app.config.errorHandler = error => errors.push(String(error));
      window.vm = app.mount('#app');
      window.waitFor = async check => { const end = performance.now() + 6000; while (!check()) { if (performance.now() > end) throw Error('Workspace UI did not settle: ' + check); await new Promise(resolve => setTimeout(resolve, 20)); } };
      window.settle = async () => { await nextTick(); await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))); };
      await waitFor(() => vm.$.setupState.workspace && !document.querySelector('.cw-loading'));
      window.setup = vm.$.setupState; window.workspace = setup.workspace;
      setup.chart.pause(); setup.alertsController.pause(); setup.listsController.pause();
      await waitFor(() => workspace.active.chart.getVisibleRange()); await settle();
      window.selectTab = async name => { [...document.querySelectorAll('.cw-sidebar [role=tab]')].find(button => button.textContent === name).click(); await settle(); };
      return { tabs: [...document.querySelectorAll('.cw-sidebar [role=tab]')].map(button => button.textContent),
        selected: document.querySelector('.cw-sidebar [aria-selected=true]').textContent,
        nativePanelButtons: document.querySelectorAll('.cw-native-tools [data-panel]').length,
        oldSettings: !!document.querySelector('.cw-header .cw-sync'), sync: workspace.sync.state(), errors };
    `)
    assert.deepEqual(initial.tabs, ['自选', '对象', '数据'])
    assert.equal(initial.selected, '自选')
    assert.equal(initial.oldSettings, false)
    assert.equal(initial.nativePanelButtons, 0)
    assert.equal(!!initial.sync.viewport, false)
    assert.equal(!!initial.sync.timeframe, false)
    assert.equal(!!initial.sync.symbol, false)
    assert.equal(initial.sync.crosshair, true)
    assert.deepEqual(initial.errors, [])

    const panels = await page.evaluate(`
      const first = workspace.active;
      window.ema = first.chart.addNativeIndicator('ema');
      await selectTab('对象');
      const hasEMA = document.querySelector('.cw-sidebar .vela-ot').textContent.includes('EMA');
      await selectTab('数据');
      const read = () => Object.fromEntries([...document.querySelectorAll('.cw-sidebar .vela-dw-row')].map(row => [row.querySelector('.vela-dw-label').textContent, row.querySelector('.vela-dw-value').textContent]));
      const before = read();
      const plot = [...first.host.querySelectorAll('canvas')].find(el => getComputedStyle(el).pointerEvents !== 'none'), rect = plot.getBoundingClientRect();
      plot.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: rect.left + rect.width * .6, clientY: rect.top + rect.height / 2 })); await settle();
      const pointed = read();
      await setup.chart.setLayout('2h');
      const second = workspace.cells()[1]; workspace.setActiveCell(second.id);
      await setup.chart.selectSymbol(catalog[1].id); await waitFor(() => second.chart.getVisibleRange()); await settle();
      const other = read();
      await selectTab('对象');
      const secondTree = document.querySelector('.cw-sidebar .vela-ot').textContent;
      workspace.setActiveCell(first.id); await settle();
      const firstTree = document.querySelector('.cw-sidebar .vela-ot').textContent;
      const saved = setup.panels.snapshot(); setup.panels.restore({ ...saved, rightTab: 'dataWindow' }); await settle();
      const restoredTab = document.querySelector('.cw-sidebar [aria-selected=true]').textContent;
      const legacy = setup.chart.snapshot(); legacy.panels = { open: 'objects', pinned: ['objects', 'dataWindow'] };
      setup.chart.restore({ state: legacy }); setup.panels.restore({ rightOpen: false, state: legacy }); await settle();
      const legacyTab = document.querySelector('.cw-sidebar [aria-selected=true]').textContent;
      const duplicateDock = !!document.querySelector('.cw-chart .vela-panel:not([hidden])');
      document.querySelector('.cw-sidebar-close').click(); await settle();
      const closed = getComputedStyle(document.querySelector('.cw-sidebar')).display === 'none';
      [...document.querySelectorAll('.cw-header > button')].find(button => button.textContent === '右侧栏').click(); await settle();
      return { hasEMA, before, pointed, other, secondTree, firstTree, savedTab: saved.rightTab, restoredTab, legacyTab, duplicateDock, closed,
        reopened: getComputedStyle(document.querySelector('.cw-sidebar')).display !== 'none', errors };
    `)
    assert.equal(panels.hasEMA, true)
    assert.ok(panels.before['收盘'])
    assert.ok(panels.pointed['收盘'])
    assert.ok(Number(panels.other['收盘'].replaceAll(',', '')) >= 200)
    assert.match(panels.secondTree, /ETH\/?USDT/)
    assert.equal(panels.secondTree.includes('EMA'), false)
    assert.equal(panels.firstTree.includes('EMA'), true)
    assert.equal(panels.savedTab, 'objects')
    assert.equal(panels.restoredTab, '数据')
    assert.equal(panels.legacyTab, '对象')
    assert.equal(panels.duplicateDock, false)
    assert.equal(panels.closed, true)
    assert.equal(panels.reopened, true)
    assert.deepEqual(panels.errors, [])

    const layout = await page.evaluate(`
      const menu = document.querySelector('.cw-layout'); menu.open = true; await settle();
      const defaultLinks = Object.fromEntries([...menu.querySelectorAll('[data-sync]')].map(input => [input.dataset.sync, input.checked]));
      menu.querySelector('[data-sync=timeframe]').click(); await settle();
      const cells = workspace.cells(); workspace.setActiveCell(cells[0].id);
      await setup.chart.setPeriod('15'); await settle(); const linked = cells.map(cell => cell.timeframe);
      menu.querySelector('[data-sync=timeframe]').click(); await settle();
      await setup.chart.setPeriod('240'); await settle(); const independent = cells.map(cell => cell.timeframe);
      const saved = setup.chart.snapshot(); setup.chart.setSync('timeframe', true); setup.chart.restore({ state: saved }); await settle();
      const restoredIndependent = !workspace.sync.get('timeframe');
      menu.querySelector('input[value="1"]').click(); await waitFor(() => setup.layout === '1'); await settle();
      const singleHasSync = !!menu.querySelector('.cw-layout-sync');
      menu.querySelector('input[value="4"]').click(); await waitFor(() => workspace.cells().length === 4); await settle(); menu.open = false;
      return { defaultLinks, linked, independent, restoredIndependent, singleHasSync, errors };
    `)
    assert.deepEqual(layout.defaultLinks, { crosshair: true, viewport: false, symbol: false, timeframe: false })
    assert.deepEqual(layout.linked, ['15', '15'])
    assert.deepEqual(layout.independent, ['240', '15'])
    assert.equal(layout.restoredIndependent, true)
    assert.equal(layout.singleHasSync, false)
    assert.deepEqual(layout.errors, [])

    const settings = await page.evaluate(`
      document.querySelector('.vela-bb-settings').click(); await settle();
      const dialog = document.querySelector('.vela-dialog--settings');
      const section = label => [...dialog.querySelectorAll('.vela-sd-tab')].find(button => button.textContent === label).click();
      const choose = async (row, label) => {
        row.querySelector('.vela-select-trigger').click(); await settle();
        [...document.querySelectorAll('.vela-select-item')].find(item => item.textContent.trim() === label).click(); await settle();
      };
      section('高级'); await settle();
      const historyRow = [...dialog.querySelectorAll('.vela-sd-row')].find(row => row.textContent.includes('历史根数'));
      const priorDepths = workspace.cells().map(cell => cell.chart.market.bars);
      await choose(historyRow, '5000'); await waitFor(() => workspace.active.chart.market.bars === 5000);
      const depths = workspace.cells().map(cell => cell.chart.market.bars);
      section('坐标轴与线条'); await settle();
      await choose(dialog.querySelector('[data-sd-id="scales.price-scale.mode"]'), '对数');
      const logarithmic = workspace.cells().map(cell => !!cell.chart.renderer.get('logScale'));
      dialog.querySelector('.vela-dialog-close').click(); await waitFor(() => !document.querySelector('.vela-dialog--settings')); await settle();
      return { priorDepths, depths, logarithmic, errors };
    `)
    assert.equal(settings.depths[0], 5000)
    assert.deepEqual(settings.depths.slice(1), settings.priorDepths.slice(1))
    assert.deepEqual(settings.logarithmic, [true, false, false, false])
    assert.deepEqual(settings.errors, [])

    const themes = await page.evaluate(`
      const { WorkspaceRenderer } = await import('/src/modules/chartWorkspace/chartPresentation.ts');
      window.openMA = async () => {
        const chart = workspace.active.chart, handle = chart.indicators().find(item => item.nativeType === 'ema');
        const renderer = WorkspaceRenderer.forHost(workspace.active.host);
        try { await waitFor(() => { renderer.openIndicatorSettings(handle.id); return !!document.querySelector('.vela-ind-dialog .cw-ma-settings'); }); }
        catch (error) { throw Error(String(error) + JSON.stringify({ handle: { id: handle.id, type: handle.nativeType }, dialog: document.querySelector('.vela-ind-dialog')?.textContent, errors })); }
        await settle();
      };
      const rgb = value => (value.match(/[\\d.]+/g) ?? []).slice(0, 3).map(Number);
      const luminance = value => rgb(value).map(channel => { const s = channel / 255; return s <= .04045 ? s / 12.92 : ((s + .055) / 1.055) ** 2.4; }).reduce((sum, channel, i) => sum + channel * [.2126,.7152,.0722][i], 0);
      const contrast = (a, b) => (Math.max(luminance(a), luminance(b)) + .05) / (Math.min(luminance(a), luminance(b)) + .05);
      window.inspectMA = () => {
        const dialog = document.querySelector('.vela-ind-dialog'), panelStyle = getComputedStyle(dialog);
        const fields = [...dialog.querySelectorAll('.cw-ma-settings input:not([type=color]), .cw-ma-settings select, .cw-ma-add')].map(field => {
          const style = getComputedStyle(field); return { color: style.color, background: style.backgroundColor, contrast: contrast(style.color, style.backgroundColor) };
        });
        const label = getComputedStyle(dialog.querySelector('.cw-ma-head'));
        const floating = getComputedStyle(document.querySelector('.cw-trading-controls'));
        return { fields, labelContrast: contrast(label.color, panelStyle.backgroundColor),
          floatingContrast: contrast(floating.color, floating.backgroundColor), floatingBackground: floating.backgroundColor,
          width: dialog.offsetWidth, height: dialog.offsetHeight };
      };
      const modes = [];
      for (const appMode of ['light', 'dark']) {
        theme.value = appMode; await settle();
        for (const plot of ['#000000', '#ffffff']) {
          workspace.active.chart.renderer.applyConfig({ layout: { background: plot } }); await settle();
          await openMA(); modes.push({ appMode, plot, ...inspectMA() });
          workspace.active.chart.renderer.closeDialogs(); await waitFor(() => !document.querySelector('.vela-ind-dialog')); await settle();
        }
      }
      theme.value = 'light'; await settle();
      const firstId = workspace.cells()[0].id; workspace.setActiveCell(firstId);
      workspace.active.chart.renderer.applyConfig({ layout: { background: '#000000' }, candles: { upColor: '#35a7ff' } });
      const saved = setup.chart.snapshot();
      await setup.chart.setLayout('1'); await setup.chart.setLayout('4'); await settle();
      const afterLayout = workspace.cells().find(cell => cell.id === firstId).chart.renderer.getConfig();
      workspace.setActiveCell(firstId); workspace.active.chart.renderer.applyConfig({ layout: { background: '#ffffff' } });
      setup.chart.restore({ state: saved }); await settle();
      const afterRestore = workspace.active.chart.renderer.getConfig();
      await openMA();
      return { modes, afterLayout: afterLayout.layout.background, afterRestore: afterRestore.layout.background,
        candleColor: afterRestore.candles.upColor, restored: inspectMA(), errors };
    `)
    for (const mode of [...themes.modes, themes.restored]) {
      assert.ok(mode.fields.every(field => field.contrast >= 4.5), JSON.stringify(mode))
      assert.ok(mode.labelContrast >= 4.5, JSON.stringify(mode))
      assert.ok(mode.floatingContrast >= 4.5, JSON.stringify(mode))
      assert.equal(mode.width, 600)
      assert.equal(mode.height, 440)
    }
    assert.equal(themes.afterLayout, '#000000')
    assert.equal(themes.afterRestore, '#000000')
    assert.equal(themes.candleColor, '#35a7ff')
    assert.deepEqual(themes.errors, [])
    if (process.env.OPENTRADING_TEST_ARTIFACTS) {
      await mkdir(process.env.OPENTRADING_TEST_ARTIFACTS, { recursive: true })
      await page.evaluate('await new Promise(resolve => setTimeout(resolve, 200))')
      await writeFile(process.env.OPENTRADING_TEST_ARTIFACTS + '/light-ui-dark-chart.png', await page.screenshot())
    }
    await page.evaluate(`workspace.active.chart.renderer.closeDialogs(); await settle();`)

    if (process.env.OPENTRADING_TEST_ARTIFACTS) {
      await mkdir(process.env.OPENTRADING_TEST_ARTIFACTS, { recursive: true })
      await page.evaluate(`await selectTab('对象'); document.querySelector('.cw-layout').open = true; await settle();`)
      await writeFile(process.env.OPENTRADING_TEST_ARTIFACTS + '/workspace-desktop.png', await page.screenshot())
      await page.evaluate(`document.querySelector('.cw-layout').open = false; await selectTab('数据'); await settle();`)
      await writeFile(process.env.OPENTRADING_TEST_ARTIFACTS + '/workspace-data.png', await page.screenshot())
    }
    await page.viewport(390, 760)
    const compact = await page.evaluate(`
      await settle();
      const sidebar = document.querySelector('.cw-sidebar'), initiallyClosed = getComputedStyle(sidebar).display === 'none';
      [...document.querySelectorAll('.cw-header > button')].find(button => button.textContent === '右侧栏').click(); await settle();
      const bounds = sidebar.getBoundingClientRect(), role = sidebar.getAttribute('role');
      await selectTab('数据'); theme.value = 'light'; await settle();
      const themeColor = getComputedStyle(sidebar).getPropertyValue('--vela-bg').trim();
      document.querySelector('.cw-sidebar [role=tab][aria-selected=true]').dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true })); await settle();
      const keyboardTab = document.querySelector('.cw-sidebar [role=tab][aria-selected=true]').textContent;
      document.querySelector('.cw-sidebar-close').click(); await settle();
      return { initiallyClosed, left: bounds.left, right: bounds.right, role, themeColor, keyboardTab,
        closed: getComputedStyle(sidebar).display === 'none', inert: document.querySelector('.cw-center').inert, errors };
    `)
    assert.equal(compact.initiallyClosed, true)
    assert.ok(compact.left >= 0 && compact.right <= 390)
    assert.equal(compact.role, 'dialog')
    assert.equal(compact.keyboardTab, '自选')
    assert.ok(compact.themeColor)
    assert.equal(compact.closed, true)
    assert.equal(compact.inert, false)
    assert.deepEqual(compact.errors, [])
    await page.evaluate('app.unmount(); await settle()')
  } finally { await page.close(); await session.close() }
})
