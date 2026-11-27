import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { browserSession } from './helpers/browserSession.mjs'

test('VIX has localized identity, a consistent icon, points and all nine periods in the real workspace', {
  timeout: 60_000, skip: !process.env.OPENTRADING_TEST_BROWSER,
}, async t => {
  const session = await browserSession(), page = await session.page(await session.context())
  t.after(async () => { await page.close(); await session.close() })
  const fixtureFile = process.env.OPENTRADING_VIX_FIXTURE
  const fixture = fixtureFile ? JSON.parse(fs.readFileSync(fixtureFile,'utf8')) : undefined
  const result = await page.evaluate(`
    const { ref, createApp, h, nextTick } = await import('/test/helpers/vuePage.ts');
    const { default: i18n } = await import('/src/i18n/index.ts'); i18n.global.locale.value = 'zh-CN';
    const { chartApi } = await import('/src/modules/chartWorkspace/api.ts');
    const { createWorkspaceChart } = await import('/src/modules/chartWorkspace/workspaceChart.ts');
    const { OpenTradingProvider } = await import('/src/modules/chartWorkspace/provider.ts');
    const { symbolName, symbolUnit } = await import('/src/modules/chartWorkspace/locale.ts');
    const { symbolIconUrl } = await import('/src/modules/chartWorkspace/symbolIcons.ts');
    const { workspacePeriodOptions } = await import('/src/modules/chartWorkspace/cellTimeframes.ts');
    const { default: Watchlist } = await import('/src/components/chartWorkspace/WorkspaceWatchlist.vue');
    const { default: Picker } = await import('/src/components/chartWorkspace/WorkspaceSymbolPicker.vue');
    const { localizeChart } = await import('/src/modules/chartWorkspace/localize.ts');
    await import('/src/style.css');
    const periods = ['1m','5m','15m','30m','1h','4h','1d','1w','1M'];
    const info = input?.['1m']?.symbol ?? { id:'index:index:US_VIX',symbol:'US_VIX',name:'Cboe Volatility Index',exchange:'CBOE',market:'index',
      currency:'PTS',timeframes:periods,session:'0200-1515:23456',timezone:'America/Chicago',aliases:['VIX','恐慌指数'],
      metadata:{ display_symbol:'VIX',name_zh:'恐慌指数',name_en:'Cboe Volatility Index',quote_unit:'points',icon_url:'/brand-icons/vix.svg',
        data_status:'delayed',mintick:.01,pricescale:100,minmove:1,has_volume:false } };
    const errors = []; window.testErrors = errors;
    chartApi.symbols = async () => [info];
    chartApi.quotes = async () => [input?.quote ?? {id:info.id,price:22.5,change:1,change_pct:4.65,updated_at:Date.now()}];
    chartApi.bars = async query => {
      const existing = input?.[query.timeframe];
      if (existing) return {...existing,bars:existing.bars.filter(bar=>bar.time<=query.end&&(query.start===undefined||bar.time>=query.start)).slice(-query.limit)};
      const unit = query.timeframe === '1M' ? 30*86400000 : query.timeframe === '1w' ? 7*86400000 : query.timeframe === '1d' ? 86400000
        : query.timeframe.endsWith('h') ? Number(query.timeframe.slice(0,-1))*3600000 : Number(query.timeframe.slice(0,-1))*60000;
      const last = Math.floor(query.end/unit)*unit;
      return {symbol:info,timeframe:query.timeframe,source:'fixture',bars:Array.from({length:Math.min(query.limit,80)},(_,i)=>{
        const time=last-(79-i)*unit;return {time,closeTime:time+unit,closed:true,open:20,high:23,low:19,close:22,volume:0};})};
    };
    OpenTradingProvider.prototype.subscribe = () => () => {};
    const host = document.createElement('div');host.style.cssText='width:1000px;height:600px';document.body.append(host);
    const control = createWorkspaceChart({host:ref(host),theme:ref('dark'),dirty(){},refreshQuotes(){},log(){},onError:e=>errors.push(String(e))});
    control.activeSymbolId.value=info.id;control.initialize([info]);
    const chart=control.workspace.value.active.chart;
    await chart.ready(); await chart.historyComplete();
    const wait=async predicate=>{const end=performance.now()+5000;while(!predicate()){if(performance.now()>end)throw new Error('VIX UI did not settle: '+JSON.stringify(errors));await new Promise(r=>setTimeout(r,20))}};
    await wait(()=>host.querySelector('.vela-sl-symbol')?.textContent.includes('恐慌指数'));
    const loaded=[];
    for (const tf of ['1','5','15','30','60','240','D','W','M']) {
      await control.setPeriod(tf); await chart.historyComplete();
      if(!chart.getVisibleRange())throw new Error('VIX chart blank at '+tf);
      loaded.push(chart.market.timeframe);
    }
    const options=workspacePeriodOptions(info).map(item=>item.value);
    const name=host.querySelector('.vela-sl-symbol').textContent;
    const image=host.querySelector('.vela-sl-logo img') ?? host.querySelector('img[src="/brand-icons/vix.svg"]');
    const icon=symbolIconUrl(info);
    const chartIcon=[...host.querySelectorAll('img')].some(image=>image.getAttribute('src')===icon);
    const controller={watchlists:ref([{id:'one',name:'我的自选'}]),watchlist:ref({id:'one',name:'我的自选'}),watchlistId:ref('one'),
      watchSymbols:ref([info.id]),pendingWatch:ref([]),quotes:ref({[info.id]:(await chartApi.quotes())[0]}),dragIndex:ref(-1),managing:ref(false)};
    const aside=document.createElement('div');document.body.append(aside);
    const app=createApp({render:()=>h(Watchlist,{controller,symbols:[info],activeSymbolId:info.id,visible:true,compact:false,width:380,embedded:true})});app.use(i18n);app.mount(aside);
    await nextTick(); const details=aside.textContent, watchIcon=aside.querySelector('img')?.getAttribute('src');
    const pickerHost=document.createElement('div');document.body.append(pickerHost);
    const picker=createApp({render:()=>h(Picker,{modelValue:true,symbols:[info],title:'addWatch'})});picker.use(i18n);picker.mount(pickerHost);await nextTick();
    const found=[...document.querySelectorAll('.symbol-results strong')].some(node=>node.textContent==='恐慌指数');
    picker.unmount();
    i18n.global.locale.value='en'; await nextTick();
    await wait(()=>host.querySelector('.vela-sl-symbol')?.textContent.includes('Cboe Volatility Index'));
    const english=host.querySelector('.vela-sl-symbol').textContent;
    const englishUnit=symbolUnit(info);
    app.unmount(); control.dispose();
    window.vixPreview={info,chartApi};
    return {loaded,options,name,english,details,found,watchIcon,icon,chartIcon,englishUnit,errors};
  `, fixture)
  assert.deepEqual(result.loaded,['1','5','15','30','60','240','D','W','M'])
  assert.deepEqual(result.options,result.loaded)
  assert.match(result.name,/恐慌指数/)
  assert.match(result.english,/Cboe Volatility Index/)
  assert.match(result.details,/恐慌指数/)
  assert.match(result.details,/点/)
  assert.doesNotMatch(result.details,/USD|US_VIX/)
  assert.equal(result.watchIcon,result.icon)
  assert.equal(result.icon,'/brand-icons/vix.svg')
  assert.equal(result.chartIcon,true)
  assert.equal(result.englishUnit,'points')
  assert.equal(result.found,true)
  assert.deepEqual(result.errors,[])
  const preview=await page.evaluate(`
    const {createApp,h,createRouter,createMemoryHistory,nextTick}=await import('/test/helpers/vuePage.ts');
    const {default:i18n}=await import('/src/i18n/index.ts');i18n.global.locale.value='zh-CN';
    const {default:Page}=await import('/src/views/ChartWorkspace.vue');
    const {researchApi}=await import('/src/modules/research/api.ts');researchApi.getWorkbench=async()=>({alerts:[]});
    await import('/src/styles/workspace-layouts.css');
    const {info,chartApi}=window.vixPreview;
    chartApi.documents=async kind=>kind==='watchlists'?[{id:'vix-watch',name:'我的自选',version:1,data:{symbols:[info.id]}}]:[];
    document.body.innerHTML='<div id="app" style="height:850px"></div>';
    const router=createRouter({history:createMemoryHistory(),routes:[{path:'/',component:{render:()=>null}}]});
    window.previewApp=createApp({render:()=>h(Page)}).use(i18n).use(router);previewApp.mount('#app');
    const end=performance.now()+8000;
    while(document.querySelector('.cw-loading')||!document.querySelector('.vela-sl-symbol')?.textContent.includes('恐慌指数')){
      if(performance.now()>end)throw new Error('Full VIX page did not settle: '+document.body.textContent);
      await new Promise(requestAnimationFrame);
    }
    await nextTick();
    return {header:document.querySelector('.cw-symbol')?.textContent,
      tradingUnit:document.querySelector('.cw-replay-quick')?.textContent,
      footer:document.querySelector('.cw-feed')?.parentElement.textContent};
  `)
  assert.match(preview.header,/恐慌指数/)
  assert.doesNotMatch(preview.tradingUnit,/USD/)
  assert.match(preview.tradingUnit,/点/)
  assert.match(preview.footer,/点/)
  if(process.env.OPENTRADING_VIX_SCREENSHOT){
    await page.viewport(1500,950)
    await new Promise(resolve=>setTimeout(resolve,200))
    fs.writeFileSync(process.env.OPENTRADING_VIX_SCREENSHOT,await page.screenshot())
  }
  await page.evaluate('previewApp.unmount()')
})
