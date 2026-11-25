import { computed, ref, watch, watchEffect, type Ref } from 'vue'
import type { WorkspaceReplay } from './workspaceReplay'
import type { WorkspacePaper } from './workspacePaper'
import type { OrderKind, OrderTarget, Side } from './replayModel'
import { cw, formatNumber } from './locale'

export type WorkspaceTradingTarget = Pick<WorkspaceReplay | WorkspacePaper,
  'account' | 'active' | 'loading' | 'symbol' | 'timeframe' | 'chart' | 'roundedPrice'>
export function createWorkspaceTradingOrders(deps: {
  target: Readonly<Ref<WorkspaceTradingTarget>>; replay: Pick<WorkspaceReplay, 'active' | 'now' | 'place'>
  paper: () => Pick<WorkspacePaper, 'place' | 'error'>; beforeChange: () => void
}) {
const t = deps.target, r = deps.replay
const menu = ref<{price:number;y:number;quantity:number}>(), menuError = ref('')
const editing = ref<OrderTarget>(), editPrice = ref(''), editQuantity = ref(0), editError = ref(''), orderError = ref('')
const stamp = () => r.active.value ? r.now.value : Date.now()
const order = computed(() => t.value.account.position ?? t.value.account.pending ?? t.value.account.draft)
const quantityStep = computed(() => Number(t.value.symbol.value?.metadata?.mincontract) || 0.00000001)
const baseCurrency = computed(() => String(t.value.symbol.value?.metadata?.basecurrency ?? ''))
const estimate = (price:number,quantity?:number) => order.value ? (price-order.value.price)*order.value.side*(quantity??order.value.quantity) : 0
const editPartial=computed(()=>editing.value!=='entry'&&order.value?.exits.find(exit=>exit.target===editing.value)?.quantity!==undefined)
async function place(side:Side,kind:OrderKind,price=t.value.account.price) {
  menu.value=undefined;orderError.value=''
  if(r.active.value){if(!r.place(side,kind,price))orderError.value=cw('replayInvalidOrder')}
  else if(!await deps.paper().place(side,kind,price))orderError.value=deps.paper().error.value||cw('replayInvalidOrder')
}
function remove(target:OrderTarget) { deps.beforeChange();orderError.value='';if (target==='entry' && t.value.account.position) t.value.account.close(stamp()); else t.value.account.cancel(target) }
function addExit(price:number) {
  menu.value=undefined
  const target=t.value.account.addExit(price,stamp())
  if(!target){orderError.value=cw('replayInvalidPrice');return}
  orderError.value=''
}
function openMenu(price:number,y:number){menu.value={price,y,quantity:order.value?.quantity??0};menuError.value=''}
function submitExitAt(){
  const value=menu.value
  if(!value)return
  if(!Number.isFinite(value.quantity)||value.quantity<=0||value.quantity>(order.value?.quantity??0)){menuError.value=cw('replayInvalidSize');return}
  if(!t.value.account.addExit(t.value.roundedPrice(value.price),stamp(),value.quantity)){menuError.value=cw('replayInvalidPrice');return}
  menu.value=undefined;orderError.value=''
}
function invalidPrice(target:OrderTarget) {
  const exit=order.value?.exits.find(exit=>exit.target===target)
  if(!exit || !order.value)return cw('replayInvalidPrice')
  const above=(order.value.side===1)===(exit.kind==='tp')
  return cw(above?'replayExitAbove':'replayExitBelow',{kind:cw(exit.kind==='tp'?'replayTP':'replaySL'),price:formatNumber(t.value.account.position?t.value.account.price:order.value.price,8)})
}
function openEditor(target:OrderTarget,price:number) {
  editing.value=target;editPrice.value=String(price);editError.value=''
  const exit=order.value?.exits.find(exit=>exit.target===target)
  editQuantity.value=exit?.quantity??0
}
function applyPrice() {
  const target=editing.value,price=t.value.roundedPrice(Number(editPrice.value))
  if(!target)return
  if(target==='entry'){if(!t.value.account.move(target,price,stamp())){editError.value=invalidPrice(target);return}}
  else {
    const quantity=editPartial.value?editQuantity.value:undefined
    if(quantity!==undefined&&(!Number.isFinite(quantity)||quantity<=0||quantity>order.value!.quantity)){editError.value=cw('replayInvalidSize');return}
    if(!t.value.account.updateExit(target,price,quantity,stamp())){editError.value=invalidPrice(target);return}
  }
  orderError.value='';editing.value=undefined
}
function move(target: OrderTarget, price: number) {
  if (!t.value.account.move(target, price, stamp())) orderError.value = invalidPrice(target)
  else orderError.value = ''
}
const stopOrder = watch(order, (value, previous) => {
  if (value !== previous) { deps.beforeChange(); editing.value=undefined;menu.value=undefined;orderError.value='' }
})
const stopEditor = watchEffect(() => { if(editing.value&&editing.value!=='entry'&&!order.value?.exits.some(exit=>exit.target===editing.value))editing.value=undefined })
return { order, menu, menuError, editing, editPrice, editQuantity, editError, orderError, quantityStep, baseCurrency, estimate, editPartial,
  place, remove, move, addExit, openMenu, submitExitAt, openEditor, applyPrice,
  dispose() { stopOrder(); stopEditor() } }
}
export type WorkspaceTradingOrders = ReturnType<typeof createWorkspaceTradingOrders>
