import type {
  PortfolioTransactionCreateCommand,
  PortfolioTransactionResponse,
} from '@/modules/tools/contracts'

const HEADERS = [
  'transactionType',
  'symbol',
  'quantity',
  'unitPrice',
  'cashAmount',
  'fee',
  'currency',
  'feeCurrency',
  'externalId',
  'note',
  'occurredAt',
] as const

const parseCsv = (text: string): string[][] => {
  const rows: string[][] = []
  let row: string[] = []
  let value = ''
  let quoted = false
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index]
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') {
        value += '"'
        index += 1
      } else if (char === '"') {
        quoted = false
      } else {
        value += char
      }
      continue
    }
    if (char === '"') quoted = true
    else if (char === ',') {
      row.push(value)
      value = ''
    } else if (char === '\n') {
      row.push(value.replace(/\r$/, ''))
      if (row.some((cell) => cell.trim())) rows.push(row)
      row = []
      value = ''
    } else value += char
  }
  row.push(value.replace(/\r$/, ''))
  if (row.some((cell) => cell.trim())) rows.push(row)
  return rows
}

const numberValue = (value: unknown) => {
  const parsed = Number(value || 0)
  if (!Number.isFinite(parsed) || parsed < 0) throw new Error(`Invalid non-negative number: ${String(value)}`)
  return parsed
}

const normalize = (value: Record<string, unknown>): PortfolioTransactionCreateCommand => {
  const transactionType = String(value.transactionType || '').trim() as PortfolioTransactionCreateCommand['transactionType']
  if (!['buy', 'sell', 'deposit', 'withdrawal', 'fee', 'transfer_in', 'transfer_out'].includes(transactionType)) {
    throw new Error(`Unsupported transactionType: ${transactionType}`)
  }
  const occurredAt = String(value.occurredAt || '').trim()
  if (!occurredAt || Number.isNaN(new Date(occurredAt).getTime())) throw new Error(`Invalid occurredAt: ${occurredAt}`)
  return {
    transactionType,
    symbol: String(value.symbol || '').trim(),
    quantity: numberValue(value.quantity),
    unitPrice: numberValue(value.unitPrice),
    cashAmount: numberValue(value.cashAmount),
    fee: numberValue(value.fee),
    currency: String(value.currency || 'USD').trim().toUpperCase(),
    feeCurrency: String(value.feeCurrency || value.currency || 'USD').trim().toUpperCase(),
    externalId: String(value.externalId || '').trim() || null,
    note: String(value.note || ''),
    metadata: {},
    occurredAt: new Date(occurredAt).toISOString(),
  }
}

export const parsePortfolioLedgerFile = async (file: File): Promise<PortfolioTransactionCreateCommand[]> => {
  const text = await file.text()
  if (file.name.toLowerCase().endsWith('.json')) {
    const parsed = JSON.parse(text) as unknown
    const rows = Array.isArray(parsed)
      ? parsed
      : parsed && typeof parsed === 'object' && Array.isArray((parsed as { transactions?: unknown }).transactions)
        ? (parsed as { transactions: unknown[] }).transactions
        : null
    if (!rows) throw new Error('JSON must be an array or contain a transactions array')
    return rows.map((row) => normalize(row as Record<string, unknown>))
  }
  const [headerRow, ...rows] = parseCsv(text)
  if (!headerRow) throw new Error('CSV is empty')
  const header = headerRow.map((value) => value.trim())
  return rows.map((cells) => normalize(Object.fromEntries(
    header.map((key, index) => [key, cells[index] || '']),
  )))
}

const escapeCsv = (value: unknown) => {
  const text = String(value ?? '')
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

export const portfolioLedgerCsv = (rows: PortfolioTransactionResponse[]) => [
  HEADERS.join(','),
  ...rows.map((row) => HEADERS.map((key) => escapeCsv(row[key])).join(',')),
].join('\r\n')

export const portfolioLedgerJson = (rows: PortfolioTransactionResponse[]) => JSON.stringify({
  schemaVersion: 1,
  exportedAt: new Date().toISOString(),
  transactions: rows.map(({ id: _id, portfolioId: _portfolioId, version: _version, archivedAt: _archivedAt, createdAt: _createdAt, updatedAt: _updatedAt, ...row }) => row),
}, null, 2)
