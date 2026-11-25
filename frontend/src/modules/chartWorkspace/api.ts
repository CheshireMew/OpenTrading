import type { ChartSymbol, ChartBars, ChartQuote, WorkspaceDocument, WorkspaceWrite, PineRun, PineRunRequest, PineRecords, PineCapabilities } from './generatedContracts'
import { ApiRequestError } from '@/api/request'
import { createBrowserDocuments } from './browserDocuments'
import { PUBLIC_SITE } from '@/app/publicSite'
import { browserPineRuns } from './browserPineRuns'
export type * from './generatedContracts'
export const BASE = '/api/v1/chart-workspace'
export async function request<T>(path:string, init:RequestInit = {}, timeoutMs = 30_000):Promise<T> {
  const controller = new AbortController()
  const stop = () => controller.abort(init.signal?.reason)
  if (init.signal?.aborted) stop(); else init.signal?.addEventListener('abort', stop, { once:true })
  const timer = setTimeout(() => controller.abort(new Error(`timeout of ${timeoutMs}ms exceeded`)), timeoutMs)
  try {
  const response = await fetch(BASE + path, { ...init, signal:controller.signal, headers:{'Content-Type':'application/json', ...init.headers} })
  const body = await response.text()
  let payload: any
  try { payload = body ? JSON.parse(body) : null } catch {
    throw new ApiRequestError('Invalid server response', { status: response.ok ? 502 : response.status })
  }
  if (!response.ok) throw new ApiRequestError(typeof payload?.detail === 'string' ? payload.detail : 'Request failed', {
    status: response.status, payload: typeof payload?.detail === 'string' ? { detail: payload.detail } : null,
  })
  if (payload === null) throw new ApiRequestError('Empty server response', { status: 502 })
  return payload as T
  } catch (cause) {
    if (controller.signal.aborted) throw controller.signal.reason ?? cause
    throw cause
  } finally { clearTimeout(timer); init.signal?.removeEventListener('abort', stop) }
}
export type DocumentKind = 'layouts'|'watchlists'|'scripts'
export const browserWorkspaceDocuments = createBrowserDocuments({
  list: kind => request<WorkspaceDocument[]>(PUBLIC_SITE ? `/defaults/${kind}` : `/${kind}`),
  version: (kind, id, version) => request<WorkspaceDocument>(`/${kind}/${encodeURIComponent(id)}?version=${version}`),
})
const pendingWrites = new Set<Promise<WorkspaceDocument>>()
export const waitForWorkspaceWrites = () => Promise.allSettled([...pendingWrites])
async function saveDocument(kind:DocumentKind,id:string,body:WorkspaceWrite) {
  const pending=browserWorkspaceDocuments.save(kind,id,body)
  pendingWrites.add(pending)
  try{return await pending}finally{pendingWrites.delete(pending)}
}
export const chartApi = {
  capabilities: () => request<PineCapabilities>('/capabilities'),
  symbols: (symbol?: string) => request<ChartSymbol[]>('/symbols' + (symbol ? '?' + new URLSearchParams({ symbol }) : ''), {}, 90_000),
  bars: (query:Record<string,string|number>, signal?:AbortSignal) => request<ChartBars>('/bars?' + new URLSearchParams(Object.entries(query).map(([k,v])=>[k,String(v)])),{signal},120_000),
  replayBars: (query:Record<string,string|number>, signal?:AbortSignal) => request<ChartBars>('/replay/bars?' + new URLSearchParams(Object.entries(query).map(([k,v])=>[k,String(v)])),{signal},120_000),
  quotes: (symbols:string[]) => request<ChartQuote[]>('/quotes?'+new URLSearchParams({symbols:symbols.join(',')}),{},120_000),
  documents: async (kind:DocumentKind) => {await waitForWorkspaceWrites();return browserWorkspaceDocuments.list(kind)},
  document: (kind:DocumentKind,id:string,version?:number) => browserWorkspaceDocuments.get(kind,id,version),
  save: saveDocument,
  remove: async (kind:DocumentKind,id:string,version:number) => {await waitForWorkspaceWrites();return browserWorkspaceDocuments.remove(kind,id,version)},
  runs: () => request<PineRun[]>('/pine-runs'),
  run: (body:PineRunRequest) => request<PineRun>('/pine-runs',{method:'POST',body:JSON.stringify(body)}),
  getRun: (id:string) => request<PineRun>(`/pine-runs/${id}`),
  cancel: (id:string) => request<PineRun>(`/pine-runs/${id}/cancel`,{method:'POST'}),
  rerun: (id:string) => request<PineRun>(`/pine-runs/${id}/rerun`,{method:'POST'}),
  records: (id:string,kind:string,offset=0,limit=200,sampled=false) => request<PineRecords>(`/pine-runs/${id}/records?${new URLSearchParams({kind,offset:String(offset),limit:String(limit),sampled:String(sampled)})}`),
  ...(PUBLIC_SITE ? browserPineRuns : {}),
}
