import type { ChartSymbol, ChartBars, ChartQuote, WorkspaceDocument, WorkspaceWrite, PineRun, PineRunRequest, PineRecords, PineCapabilities } from './generatedContracts'
export type * from './generatedContracts'
export const BASE = '/api/v1/chart-workspace'
export async function request<T>(path:string, init:RequestInit = {}):Promise<T> {
  const response = await fetch(BASE + path, { ...init, headers:{'Content-Type':'application/json', ...init.headers} })
  const payload = await response.json()
  if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : `请求失败 (${response.status})`)
  return payload as T
}
export type DocumentKind = 'layouts'|'watchlists'|'scripts'
const pendingWrites = new Set<Promise<WorkspaceDocument>>()
async function saveDocument(kind:DocumentKind,id:string,body:WorkspaceWrite) {
  const pending=request<WorkspaceDocument>(`/${kind}/${encodeURIComponent(id)}`,{method:'PUT',body:JSON.stringify(body)})
  pendingWrites.add(pending)
  try{return await pending}finally{pendingWrites.delete(pending)}
}
export const chartApi = {
  capabilities: () => request<PineCapabilities>('/capabilities'),
  symbols: () => request<ChartSymbol[]>('/symbols'),
  bars: (query:Record<string,string|number>, signal?:AbortSignal) => request<ChartBars>('/bars?' + new URLSearchParams(Object.entries(query).map(([k,v])=>[k,String(v)])),{signal}),
  quotes: (symbols:string[]) => request<ChartQuote[]>('/quotes?'+new URLSearchParams({symbols:symbols.join(',')})),
  documents: async (kind:DocumentKind) => {await Promise.allSettled([...pendingWrites]);return request<WorkspaceDocument[]>(`/${kind}`)},
  save: saveDocument,
  archive: (kind:DocumentKind,id:string) => request(`/${kind}/${encodeURIComponent(id)}/archive`,{method:'POST'}),
  runs: () => request<PineRun[]>('/pine-runs'),
  run: (body:PineRunRequest) => request<PineRun>('/pine-runs',{method:'POST',body:JSON.stringify(body)}),
  getRun: (id:string) => request<PineRun>(`/pine-runs/${id}`),
  cancel: (id:string) => request<PineRun>(`/pine-runs/${id}/cancel`,{method:'POST'}),
  rerun: (id:string) => request<PineRun>(`/pine-runs/${id}/rerun`,{method:'POST'}),
  records: (id:string,kind:string,offset=0,limit=200) => request<PineRecords>(`/pine-runs/${id}/records?${new URLSearchParams({kind,offset:String(offset),limit:String(limit)})}`),
}
