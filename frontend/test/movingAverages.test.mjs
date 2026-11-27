import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import ts from 'typescript'
import { browserSession } from './helpers/browserSession.mjs'

function setup() {
  const descriptors = new Map(), instances = [], output = []
  for (const type of ['sma', 'ema']) descriptors.set(type, {
    type, shortTitle: type.toUpperCase(), overlay: true, paneHint: 'price',
    inputsSchema: () => [{ key: 'length', type: 'int', defval: 20 }],
    defaultInputs: () => ({ length: 20, source: 'Close', offset: 0, color: '#3786ff' }),
    create() {
      const state = { updates: 0, stopped: 0, suspended: 0, bars: 0 }
      instances.push(state)
      const emit = () => state.ctx.emit({ series: [{ id: 'same-native-series-id', title: type, kind: 'line', points: [], style: { color: state.values.color } }] })
      return {
        start(ctx, values) { state.ctx = ctx; state.values = values; emit() },
        setInputs(values) { state.values = values; state.updates++; emit() },
        onBars() { state.bars++; emit() }, onViewport() {},
        suspend() { state.suspended++ }, resume: emit, stop() { state.stopped++ },
      }
    },
  })
  const code = ts.transpileModule(readFileSync(new URL('../src/modules/chartWorkspace/movingAverages.ts', import.meta.url), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText
  const exports = {}
  new Function('require', 'exports', code)(() => ({ getNativeIndicator: type => descriptors.get(type), registerNativeIndicator: descriptor => descriptors.set(descriptor.type, descriptor) }), exports)
  exports.registerMovingAverageDefinitions()
  return { ...exports, descriptors, instances, output, context: { id: 'ma1', emit: value => output.push(value) } }
}

test('moving averages retain legacy inputs and safely read saved additional lines', () => {
  const { movingAverageLines } = setup()
  const legacy = { length: 120, source: 'Open', offset: -2, color: '#ff0000' }
  assert.deepEqual(movingAverageLines(legacy), [{ id: 'primary', ...legacy }])
  assert.deepEqual(movingAverageLines({ ...legacy, additionalLines: '{invalid' }), [{ id: 'primary', ...legacy }])
  const lines = movingAverageLines({ ...legacy, additionalLines: JSON.stringify([
    { id: 'primary', length: 200, color: '#00ff00' }, { id: 'primary', length: 60 },
  ]) })
  assert.deepEqual(lines.map(line => line.length), [120, 200, 60])
  assert.ok(lines.every(line => line.source === 'Open'))
  assert.equal(new Set(lines.map(line => line.id)).size, 3)
})

test('each average line owns its native inputs and stable series while updates are batched', () => {
  const { descriptors, registerMovingAverageDefinitions, instances, output, context } = setup()
  const descriptor = descriptors.get('ema')
  registerMovingAverageDefinitions(); assert.equal(descriptors.get('ema'), descriptor)
  const instance = descriptor.create(), inputs = { ...descriptor.defaultInputs(), additionalLines: JSON.stringify([
    { id: 'slow', length: 120, source: 'Open', offset: 1, color: '#ff0000' },
    { id: 'long', length: 200, source: 'High', offset: -2, color: '#00ff00' },
  ]) }
  instance.start(context, inputs)
  assert.equal(output.length, 1)
  assert.deepEqual(instances.map(child => child.values.length), [20, 120, 200])
  assert.deepEqual(instances.map(child => child.values.source), ['Close', 'Close', 'Close'])
  assert.deepEqual(instances.map(child => child.values.offset), [0, 1, -2])
  assert.equal(new Set(output.at(-1).series.map(series => series.id)).size, 3)
  const ids = output.at(-1).series.map(series => series.id)
  instance.setInputs({ color: '#123456' })
  assert.deepEqual(instances.map(child => child.updates), [1, 0, 0])
  assert.deepEqual(output.at(-1).series.map(series => series.id), ids)
  instance.setInputs({ source: 'Low' })
  assert.deepEqual(instances.map(child => child.values.source), ['Low', 'Low', 'Low'])
  instance.onBars(); assert.deepEqual(instances.map(child => child.bars), [1, 1, 1])
  const before = output.length
  instance.suspend(); instance.onBars(); assert.equal(output.length, before)
  instance.resume(); assert.equal(output.length, before + 1)
  instance.setInputs({ additionalLines: '[]' })
  assert.deepEqual(instances.map(child => child.stopped), [0, 1, 1])
  assert.equal(output.at(-1).series.length, 1)
  instance.stop(); assert.deepEqual(instances.map(child => child.stopped), [1, 1, 1])
})

let session
after(async () => { await session?.close() })
const browserOptions = { timeout: 45_000, skip: process.env.OPENTRADING_TEST_COLLECT === '1' || !process.env.OPENTRADING_TEST_BROWSER }

test('MA and EMA edit compact rows in a fixed dialog, cancel/reset, and restore their saved layout', browserOptions, async () => {
  session ??= await browserSession()
  const page = await session.page(await session.context())
  try {
    const result = await page.evaluate(`
      const {VelaWorkspace, getNativeIndicator} = await import('/test/helpers/nativeIndicatorsPage.ts');
      const {WorkspaceRenderer} = await import('/src/modules/chartWorkspace/chartPresentation.ts');
      const {registerMovingAverageDefinitions} = await import('/src/modules/chartWorkspace/movingAverages.ts');
      const {installIndicatorHelp} = await import('/src/modules/chartWorkspace/indicatorHelp.ts');
      const {localizeChart} = await import('/src/modules/chartWorkspace/localize.ts');
      const i18n = (await import('/src/i18n/index.ts')).default; i18n.global.locale.value='zh-CN';
      const theme = (await import('/src/composables/useTheme.ts')).useTheme().theme; theme.value='dark';
      await import('/src/style.css');await import('/src/views/ChartWorkspace.vue');
      const shell=document.createElement('section');shell.className='chart-workspace';shell.style.cssText='width:1100px;height:740px';
      const host=document.createElement('div');host.className='cw-chart';shell.append(host);document.body.append(shell);
      const bars=Array.from({length:350},(_,i)=>({time:Date.UTC(2026,0,1)+i*3600000,open:90+i*.2,high:104+i*.2,low:85+i*.2,close:100+i*.2,volume:10}));
      const workspace=new VelaWorkspace(host,{symbol:'TEST',timeframe:'60',data:bars,live:false,volume:false,watermark:false,persist:false,renderer:WorkspaceRenderer});
      const originals=new Map(['sma','ema'].map(type=>[type,getNativeIndicator(type)]));
      registerMovingAverageDefinitions();
      const offHelp=installIndicatorHelp(host,()=>workspace), offLocale=localizeChart(host);
      const chart=workspace.active.chart, renderer=WorkspaceRenderer.forHost(workspace.active.host);
      const settle=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      const rows=()=>[...host.querySelectorAll('.cw-ma-row:not(.cw-ma-head)')];
      const open=async handle=>{const end=performance.now()+5000;while(true){renderer.openIndicatorSettings(handle.id);await settle();if(host.querySelector('.vela-ind-dialog'))return;if(performance.now()>end)throw Error('Indicator settings unavailable: '+host.innerText);await new Promise(resolve=>setTimeout(resolve,30));}};
      const change=(index,field,value)=>{const control=rows()[index].querySelector('[data-field='+field+']');control.value=value;control.dispatchEvent(new Event(field==='color'?'input':'change',{bubbles:true}));};
      const footer=index=>host.querySelectorAll('.vela-ind-dialog .vela-dialog-footer button')[index].click();
      const renderOutput=(descriptor,inputs)=>{let result;const instance=descriptor.create();instance.start({id:'expected',symbol:'TEST',timeframe:'60',live:false,bars:()=>bars,emit:output=>result=output,pushData(){},setStatus(){}},inputs);instance.stop();return result;};
      const checked=[];
      try{
        for(const type of ['sma','ema']){
          const handle=chart.addNativeIndicator(type);handle.setInputs({length:20,source:'Close',offset:0,color:'#3786ff'});
          await open(handle);
          const initialHeight=host.querySelector('.vela-ind-dialog').offsetHeight;
          const compact=rows().every(row=>[...row.querySelectorAll('input,select')].every(control=>Math.abs(control.getBoundingClientRect().top-row.querySelector('input').getBoundingClientRect().top)<2));
          host.querySelector('.cw-ma-add').click();host.querySelector('.cw-ma-add').click();
          change(1,'length','120');change(2,'length','200');change(1,'offset','1');change(2,'color','#ff0000');
          const sourceControl=host.querySelector('[data-ma-source]');sourceControl.value='Open';sourceControl.dispatchEvent(new Event('change',{bubbles:true}));await settle();
          const multiHeight=host.querySelector('.vela-ind-dialog').offsetHeight;
          const before=JSON.parse(JSON.stringify(handle.inputValues()));
          const output=renderOutput(getNativeIndicator(type),before);
          const extras=JSON.parse(before.additionalLines), lines=[before,...extras];
          const maths=output.series.every((series,index)=>JSON.stringify(series.points)===JSON.stringify(renderOutput(originals.get(type),{...lines[index],source:before.source}).series[0].points));
          const uniqueIds=new Set(output.series.map(series=>series.id)).size===3;
          footer(2);await settle();
          await open(handle);rows()[0].querySelector('.cw-ma-remove').click();await settle();const promoted=Number(rows()[0].querySelector('[data-field=length]').value);
          footer(1);await settle();const cancelled=JSON.stringify(handle.inputValues())===JSON.stringify(before);
          await open(handle);footer(0);await settle();const reset=rows().length===1&&rows()[0].querySelector('[data-field=length]').value==='20';footer(1);await settle();
          const resetCancelled=JSON.stringify(handle.inputValues())===JSON.stringify(before);
          const state=workspace.getState();handle.setInputs({additionalLines:'[]'});workspace.applyState(state);await settle();
          const restored=chart.indicators().find(item=>item.nativeType===type);await open(restored);
          const savedLengths=rows().map(row=>Number(row.querySelector('[data-field=length]').value));
          const geometry=renderer.readFeature('opentrading.indicatorPicking').geometry(restored.id);
          checked.push({type,initialHeight,multiHeight,compact,maths,uniqueIds,promoted,cancelled,reset,resetCancelled,savedLengths,sharedSource:host.querySelectorAll('[data-ma-source]').length===1&&host.querySelector('[data-ma-source]').value==='Open',paintedLines:geometry.length});
          footer(2);await settle();
        }
        return checked;
      }finally{offHelp();offLocale();workspace.destroy();shell.remove();}
    `)
    for (const item of result) {
      assert.equal(item.initialHeight, 440, JSON.stringify(item));assert.equal(item.multiHeight, item.initialHeight, JSON.stringify(item))
      assert.equal(item.compact, true, JSON.stringify(item));assert.equal(item.maths, true, JSON.stringify(item));assert.equal(item.uniqueIds, true, JSON.stringify(item))
      assert.equal(item.promoted, 120, JSON.stringify(item));assert.equal(item.cancelled, true, JSON.stringify(item));assert.equal(item.reset, true, JSON.stringify(item));assert.equal(item.resetCancelled, true, JSON.stringify(item))
      assert.deepEqual(item.savedLengths, [20, 120, 200]);assert.equal(item.paintedLines, 3)
      assert.equal(item.sharedSource, true)
    }
  } finally { await page.close() }
})
