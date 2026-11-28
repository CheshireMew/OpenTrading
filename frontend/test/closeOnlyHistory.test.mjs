import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import { browserSession } from './helpers/browserSession.mjs'

async function verifyHistory(t,fixture) {
  const session=await browserSession(), page=await session.page(await session.context())
  t.after(async()=>{await page.close();await session.close()})
  const initial=await page.evaluate(`
    const {ref,nextTick}=await import('/test/helpers/vuePage.ts');
    const {default:i18n}=await import('/src/i18n/index.ts');i18n.global.locale.value='zh-CN';
    const {chartApi}=await import('/src/modules/chartWorkspace/api.ts');
    const {OpenTradingProvider}=await import('/src/modules/chartWorkspace/provider.ts');
    const {createWorkspaceChart}=await import('/src/modules/chartWorkspace/workspaceChart.ts');
    await import('/src/style.css');
    const day=86400000, end=Math.floor(Date.now()/day)*day;
    window.info=input?.symbol??{id:'index:index:US_NASDAQ_COMP',symbol:'US_NASDAQ_COMP',name:'Nasdaq Composite Index',exchange:'NASDAQ',market:'index',currency:'PTS',
      timeframes:['1d','1w','1M'],timezone:'America/New_York',session:'0930-1600:23456',close_only:false,
      metadata:{name_zh:'纳斯达克综合指数',name_en:'Nasdaq Composite Index',display_symbol:'IXIC',quote_unit:'points',icon_url:'/brand-icons/ixic.svg',pricescale:100,mintick:.01,has_volume:false}};
    window.rows=input?.bars??Array.from({length:4200},(_,i)=>{
      const time=end-(4199-i)*day, close=3000+i%200;
      return {time,closeTime:time+day,open:i<2000?close:close-5,high:i<2000?close:close+10,low:i<2000?close:close-10,close,volume:0,closed:true,closeOnly:i<2000};
    });
    window.queries=[];window.events=[];window.errors=[];window.closeHints=[];
    const fillText=CanvasRenderingContext2D.prototype.fillText;
    CanvasRenderingContext2D.prototype.fillText=function(text,...args){
      if(String(text).includes('该区间仅提供收盘价'))closeHints.push(String(text));
      return fillText.call(this,text,...args);
    };
    chartApi.symbols=async()=>[info];chartApi.quotes=async()=>[];
    chartApi.bars=async query=>{
      queries.push(query);await new Promise(resolve=>setTimeout(resolve,5));
      const bars=rows.filter(bar=>bar.time<=query.end&&(query.start===undefined||bar.time>=query.start)).slice(-query.limit);
      // Older API responses used a page flag. Even a stale cached response
      // must not replace the stable catalog capability or chosen price style.
      return {symbol:{...info,close_only:bars.length>0&&bars.every(bar=>bar.closeOnly)},timeframe:query.timeframe,source:'history',bars};
    };
    OpenTradingProvider.prototype.subscribe=()=>()=>{};
    const shell=document.createElement('section');shell.className='chart-workspace cw-dark';shell.style.cssText='width:1200px;height:700px';
    (document.getElementById('app')??document.body).replaceChildren(shell);
    const host=document.createElement('div');host.className='cw-chart';host.style.cssText='width:1200px;height:700px';shell.append(host);
    window.host=host;
    window.control=createWorkspaceChart({host:ref(host),theme:ref('dark'),dirty(){},refreshQuotes(){},log(){},onError:e=>errors.push(String(e))});
    control.activeSymbolId.value=info.id;control.activeTimeframe.value='D';control.historyDepth.value=500;
    control.initialize([info]);window.chart=control.workspace.value.active.chart;
    chart.on('history:complete',event=>events.push(event));
    await chart.ready();await control.setPeriod('D');await chart.setMarket({bars:500});await chart.historyComplete();
    window.wait=async predicate=>{const until=performance.now()+6000;while(!predicate()){if(performance.now()>until)throw new Error('Pan did not settle: '+JSON.stringify({events,errors}));await new Promise(resolve=>setTimeout(resolve,15));}};
    window.settled=async()=>{let promise;do{promise=chart.historyComplete();await promise;}while(promise!==chart.historyComplete())};
    await settled();
    return {style:control.snapshot().charts[0].priceStyle,timeframe:chart.market.timeframe,loaded:events.at(-1).barsLoaded};
  `,fixture)
  assert.equal(initial.style,'candles')
  assert.equal(initial.timeframe,'D')
  const result=await page.evaluate(`
    window.publishedOnly=rows.every(bar=>!bar.closeOnly);
    for(let turn=0;turn<(publishedOnly?6:3);turn++){
      const oldest=events.at(-1).oldestTime;
      if(oldest===rows[0].time)break;
      chart.setVisibleRange({from:oldest-10*86400000,to:oldest+40*86400000});
      await wait(()=>events.at(-1).oldestTime<oldest);await settled();
      if(queries.some(query=>query.end<rows.find(bar=>!bar.closeOnly).time))break;
    }
    const old=rows.filter(bar=>bar.closeOnly), middle=publishedOnly?rows[0].time:old[Math.floor(old.length*.75)].time;
    chart.setVisibleRange({from:middle-30*86400000,to:middle+30*86400000});
    await wait(()=>events.at(-1).oldestTime<=(publishedOnly?middle:middle-30*86400000));await settled();
    await settled();await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    return {style:control.snapshot().charts[0].priceStyle,capability:control.symbols.value[0].close_only,
      loaded:events.at(-1).barsLoaded,state:events.at(-1).reason,range:chart.getVisibleRange(),
      closeOnlyPages:queries.filter(query=>query.end<rows.find(bar=>!bar.closeOnly).time).length,closeHints:closeHints.length,
      publishedOnly,oldest:events.at(-1).oldestTime,visible:host.getBoundingClientRect().top<innerHeight,errors};
  `)
  assert.equal(result.style,'candles')
  assert.equal(result.capability,false)
  assert.ok(result.loaded>1000)
  assert.notEqual(result.state,'aborted')
  if(result.publishedOnly){
    assert.equal(result.oldest,fixture.bars[0].time,'Panning must stop at the first published observation')
    assert.equal(result.loaded,fixture.bars.length)
    assert.equal(result.closeHints,0)
  }else{
    assert.ok(result.closeOnlyPages>0)
    assert.ok(result.closeHints>0,'The close-only history must remain visibly represented')
  }
  assert.equal(result.visible,true)
  assert.deepEqual(result.errors,[])
  const screenshot=result.publishedOnly?process.env.OPENTRADING_PUBLISHED_INDEX_SCREENSHOT:process.env.OPENTRADING_CLOSE_ONLY_SCREENSHOT
  if(screenshot){
    await page.viewport(1280,760)
    await page.evaluate(`
      const split=rows.find(bar=>!bar.closeOnly).time;
      chart.setVisibleRange({from:split-100*86400000,to:split+100*86400000});
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
    `)
    fs.writeFileSync(screenshot,await page.screenshot())
  }
  const selected=await page.evaluate(`
    control.workspace.value.context().setPriceStyle('line');await settled();
    await chart.setMarket({bars:chart.market.bars+100});await settled();
    return {style:control.snapshot().charts[0].priceStyle,errors};
  `)
  assert.equal(selected.style,'line')
  assert.deepEqual(selected.errors,[])
  await page.evaluate('control.dispose()')
}

test('panning into published close-only history preserves candles, the viewport, and a completed load',{
  timeout:60_000,skip:!process.env.OPENTRADING_TEST_BROWSER,
},async t=>{
  const file=process.env.OPENTRADING_CLOSE_ONLY_FIXTURE
  await verifyHistory(t,file?JSON.parse(fs.readFileSync(file,'utf8')):undefined)
})

test('published HSTECH history ends at launch with candles intact',{
  timeout:60_000,skip:!process.env.OPENTRADING_TEST_BROWSER,
},async t=>{
  const file=process.env.OPENTRADING_PUBLISHED_INDEX_FIXTURE
  const fixture=file?JSON.parse(fs.readFileSync(file,'utf8')):{
    symbol:{id:'index:index:HK_HSTECH',symbol:'HK_HSTECH',name:'Hang Seng TECH Index',exchange:'HSI',
      market:'index',currency:'PTS',timeframes:['1d','1w','1M'],timezone:'Asia/Hong_Kong',
      session:'0930-1200,1300-1600:23456',close_only:false,
      metadata:{name_zh:'恒生科技指数',name_en:'Hang Seng TECH Index',display_symbol:'HSTECH',
        quote_unit:'points',icon_url:'/brand-icons/hstech.svg',pricescale:100,mintick:.01,has_volume:false}},
    bars:Array.from({length:1500},(_,i)=>{
      const time=Date.UTC(2020,6,27)+i*86400000,close=6500+i%200
      return {time,closeTime:time+86400000,open:close-5,high:close+10,low:close-10,close,
        volume:0,closed:true,closeOnly:false}
    }),
  }
  await verifyHistory(t,fixture)
})
