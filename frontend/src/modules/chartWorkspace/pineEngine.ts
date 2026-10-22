import type { ScriptingEngine, PreparedScript, ExecutionRequest, ExecutionHandlers, ExecutionSession } from '@luxalgo/vela/plugin'
import PineWorker from './pine.worker?worker'
import { checkPine, pineError, PINE_ENGINE_VERSION } from './pineCompatibility.mjs'
import type { ChartSymbol } from './api'
import { cw,messageText } from './locale'

type Prepared = PreparedScript & { token:{source:string;instanceId:string} }
export function readPineMetadata(source:string):{result:Promise<{kind:string;inputs:any[];props:Record<string,any>}>;cancel:()=>void} {
  const worker=new PineWorker()
  let stop:()=>void=()=>{}
  const result=new Promise<{kind:string;inputs:any[];props:Record<string,any>}>((resolve,reject)=>{
    const timer=setTimeout(()=>{stop();reject(new Error(cw('parseTimeout')))},60000)
    stop=()=>{clearTimeout(timer);worker.terminate()}
    worker.onerror=e=>{stop();reject(new Error(e.message))}
    worker.onmessage=({data})=>{if(data.type==='metadata'){stop();resolve(data)}else if(data.type==='error'){stop();reject(pineError(data))}}
    worker.postMessage({type:'metadata',source})
  })
  return {result,cancel:stop}
}
class WorkerSession {
  worker=new PineWorker()
  stopped=false
  private timer:ReturnType<typeof setTimeout>|undefined
  private rejectPrepare:((error:Error)=>void)|undefined
  private contextId=0
  private contexts=new Map<number,(value:any)=>void>()
  handlers?:ExecutionHandlers
  request?:ExecutionRequest
  constructor(){this.worker.onerror=e=>this.fail(new Error(e.message));this.worker.onmessage=async({data})=>{
    if(this.stopped)return
    if(data.type==='model'){this.done();this.handlers?.onModel(data.model)}
    else if(data.type==='error')this.fail(pineError(data))
    else if(data.type==='warning'){
      if(/not (implemented|supported)|unsupported/i.test(data.warning.message))this.fail(new Error(cw('unsupportedFunction',{detail:data.warning.message})))
      else this.handlers?.onWarning?.(data.warning)
    }
    else if(data.type==='alert')this.handlers?.onAlert?.(data.alert)
    else if(data.type==='done'){this.done();this.handlers?.onDone?.()}
    else if(data.type==='context'){this.contexts.get(data.id)?.(data.value);this.contexts.delete(data.id)}
    else if(data.type==='fetch'){
      try{if(!this.request?.fetchSeries)throw new Error(cw('noMultiframe'));const [symbol,timeframe,range]=data.args;const bars=await this.request.fetchSeries(symbol,timeframe,range);this.post({type:'fetchResult',id:data.id,bars})}
      catch(e){this.post({type:'fetchResult',id:data.id,error:String(e)})}
    }
  }}
  post(message:unknown){if(!this.stopped)this.worker.postMessage(message)}
  arm(){if(this.timer)return;this.timer=setTimeout(()=>this.fail(new Error(cw('computeTimeout'))),60000)}
  done(){clearTimeout(this.timer);this.timer=undefined}
  fail(error:Error){error.message=messageText(error.message);this.rejectPrepare?.(error);this.handlers?.onError?.(error);this.stop()}
  prepare(source:string,instanceId:string):Promise<PreparedScript>{this.arm();return new Promise((resolve,reject)=>{
    this.rejectPrepare=reject
    const listener=({data}:MessageEvent)=>{if(data.type!=='prepared')return;this.worker.removeEventListener('message',listener);this.done();this.rejectPrepare=undefined;if(data.version!==PINE_ENGINE_VERSION){reject(new Error(cw('versionMismatch')));this.stop();return}resolve(data.prepared)}
    this.worker.addEventListener('message',listener);this.post({type:'prepare',source,instanceId})
  })}
  stop(){if(this.stopped)return;this.stopped=true;this.done();this.worker.terminate();for(const done of this.contexts.values())done(null);this.contexts.clear()}
  context(select:unknown){return new Promise<any>(resolve=>{if(this.stopped){resolve(null);return}const id=++this.contextId;this.contexts.set(id,resolve);this.post({type:'context',id,select})})}
}

export class OpenTradingPineEngine implements ScriptingEngine {
  constructor(private catalog:()=>ChartSymbol[]=()=>[]){}
  readonly language='pine'
  readonly capabilities={streaming:true,visibleRange:true,inputs:true,props:true}
  private sessions=new Set<WorkerSession>()
  async prepare(source:string,instanceId:string):Promise<PreparedScript>{
    checkPine(source)
    const worker=new WorkerSession();this.sessions.add(worker)
    try{const prepared=await worker.prepare(source,instanceId);return {...prepared,token:{source,instanceId}}}
    finally{worker.stop();this.sessions.delete(worker)}
  }
  execute(request:ExecutionRequest,handlers:ExecutionHandlers):ExecutionSession{
    const worker=new WorkerSession();worker.request=request;worker.handlers=handlers;this.sessions.add(worker)
    const prepared=request.prepared as Prepared
    let ready=false
    const waiting:unknown[]=[]
    const post=(value:unknown)=>{if(ready)worker.post(value);else waiting.push(value)}
    void worker.prepare(prepared.token.source,prepared.token.instanceId).then(p=>{
      if(worker.stopped)return
      const {getBars,fetchSeries,...plain}=request
      worker.arm();worker.post({type:'execute',catalog:JSON.parse(JSON.stringify(this.catalog())),request:{...plain,prepared:p}});ready=true
      for(const item of waiting)worker.post(item)
    }).catch(error=>{handlers.onError?.(error);worker.stop();this.sessions.delete(worker)})
    return {
      stop:()=>{worker.stop();this.sessions.delete(worker)},
      update:(inputs,props)=>{worker.arm();post({type:'update',inputs,props})},
      setVisibleRange:range=>post({type:'range',range}),
      notifyBars:reason=>{if(reason==='backfill')return;const bars=request.getBars?.()??request.bars;if(!bars.length)return;worker.arm();const full=reason==='complete';post({type:'bars',bars:full?bars:bars.slice(-2),reason,full})},
      getContext:select=>worker.context(select),
    }
  }
  terminate(){for(const session of this.sessions)session.stop();this.sessions.clear()}
}
