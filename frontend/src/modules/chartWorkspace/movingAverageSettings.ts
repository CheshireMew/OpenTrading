import type { InputSchema, InputValue } from '@luxalgo/vela'
import { cw } from './locale'
import { MA_COLORS, MA_LINES_KEY, MA_SOURCES, movingAverageLines } from './movingAverages'

export type IndicatorSettingsDetail = {
  id: string
  values: Record<string, InputValue>
  propValues: Record<string, InputValue>
  tabs: { name: string; inputs: InputSchema[]; body: HTMLElement }[]
  inputBody?: HTMLElement
  commit: (key: string, value: InputValue) => void
}

export function configureMovingAverageSettings(type: string | undefined, detail: IndicatorSettingsDetail) {
  if (type !== 'sma' && type !== 'ema') return
  const body = document.createElement('div')
  body.className = 'cw-ma-settings'
  const lines = movingAverageLines(detail.values)
  const fields = ['length', 'offset', 'color'] as const
  const commitExtras = () => detail.commit(MA_LINES_KEY, JSON.stringify(lines.slice(1).map(({ id, length, offset, color }) => ({ id, length, offset, color }))))
  const update = (index: number, key: typeof fields[number], value: InputValue) => {
    Object.assign(lines[index]!, { [key]: value })
    if (index === 0) detail.commit(key, value)
    else commitExtras()
  }
  const render = () => {
    body.replaceChildren()
    const sourceLabel = document.createElement('label'), sourceTitle = document.createElement('span'), sourceControl = document.createElement('select')
    sourceLabel.className = 'cw-ma-source'; sourceTitle.textContent = cw('maSource')
    sourceControl.dataset.maSource = ''; sourceControl.setAttribute('aria-label', cw('maSource'))
    for (const source of MA_SOURCES) { const option = document.createElement('option'); option.value = source; option.textContent = source; sourceControl.append(option) }
    sourceControl.value = lines[0]!.source
    sourceControl.addEventListener('change', () => {
      for (const line of lines) line.source = sourceControl.value
      detail.commit('source', sourceControl.value)
    })
    sourceLabel.append(sourceTitle, sourceControl)
    const table = document.createElement('div')
    table.className = 'cw-ma-table'; table.setAttribute('role', 'table')
    const header = document.createElement('div')
    header.className = 'cw-ma-row cw-ma-head'; header.setAttribute('role', 'row')
    for (const key of fields) {
      const label = document.createElement('span'); label.setAttribute('role', 'columnheader')
      label.textContent = cw('ma' + key[0]!.toUpperCase() + key.slice(1)); header.append(label)
    }
    const actions = document.createElement('span'); actions.setAttribute('role', 'columnheader'); header.append(actions)
    table.append(header)
    lines.forEach((line, index) => {
      const row = document.createElement('div')
      row.className = 'cw-ma-row'; row.setAttribute('role', 'row'); row.dataset.lineId = line.id
      for (const key of fields) {
        const cell = document.createElement('span'); cell.setAttribute('role', 'cell')
        const control = document.createElement('input')
        control.dataset.field = key
        control.setAttribute('aria-label', `${type === 'sma' ? 'MA' : 'EMA'} ${index + 1} · ${cw('ma' + key[0]!.toUpperCase() + key.slice(1))}`)
        control.type = key === 'color' ? 'color' : 'number'
        if (key !== 'color') { control.min = key === 'length' ? '1' : '-500'; control.max = key === 'length' ? '5000' : '500'; control.step = '1' }
        control.value = String(line[key])
        control.addEventListener(key === 'color' ? 'input' : 'change', () => {
          if (!control.checkValidity() || !control.value) { control.value = String(line[key]); return }
          update(index, key, key === 'length' || key === 'offset' ? Number(control.value) : control.value)
        })
        cell.append(control); row.append(cell)
      }
      const removeCell = document.createElement('span'), remove = document.createElement('button')
      removeCell.setAttribute('role', 'cell'); remove.type = 'button'; remove.className = 'cw-ma-remove'; remove.textContent = '×'
      remove.disabled = lines.length === 1
      remove.setAttribute('aria-label', cw('maRemoveLine', { length: line.length })); remove.title = cw('maRemoveLine', { length: line.length })
      remove.addEventListener('click', () => {
        lines.splice(index, 1)
        if (index === 0) for (const key of fields) detail.commit(key, lines[0]![key])
        commitExtras(); render()
      })
      removeCell.append(remove); row.append(removeCell); table.append(row)
    })
    const add = document.createElement('button')
    add.type = 'button'; add.className = 'cw-ma-add'; add.textContent = '+ ' + cw('maAddLine')
    add.addEventListener('click', () => {
      const length = [60, 120, 200].find(length => !lines.some(line => line.length === length)) ?? 20
      lines.push({ id: crypto.randomUUID(), length, source: lines[0]!.source, offset: 0, color: MA_COLORS[lines.length % MA_COLORS.length]! })
      commitExtras(); render()
      const input = body.querySelector<HTMLInputElement>('.cw-ma-row:last-child input[data-field=length]')
      input?.focus(); input?.select()
    })
    body.append(sourceLabel, table, add)
  }
  render(); detail.inputBody = body
}
