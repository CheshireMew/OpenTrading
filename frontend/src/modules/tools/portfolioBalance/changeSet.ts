import type { PortfolioCollectionChangeCommand } from '../contracts'
import type { PortfolioBalanceSnapshot } from './types'

export const clonePortfolioSnapshot = (
  snapshot: PortfolioBalanceSnapshot,
): PortfolioBalanceSnapshot => structuredClone(snapshot)

const sameOrder = (left: string[], right: string[]) => (
  left.length === right.length && left.every((value, index) => value === right[index])
)

export const buildPortfolioChangeCommand = (
  current: PortfolioBalanceSnapshot,
  acknowledged: PortfolioBalanceSnapshot,
  expectedRevision: number,
): PortfolioCollectionChangeCommand | null => {
  const acknowledgedById = new Map(
    acknowledged.portfolios.map((portfolio) => [portfolio.id, portfolio] as const),
  )
  const changedPortfolios = current.portfolios.filter((portfolio) => {
    const previous = acknowledgedById.get(portfolio.id)
    return previous === undefined || JSON.stringify(previous) !== JSON.stringify(portfolio)
  })
  const portfolioOrder = current.portfolios.map((portfolio) => portfolio.id)
  const acknowledgedOrder = acknowledged.portfolios.map((portfolio) => portfolio.id)

  if (
    changedPortfolios.length === 0
    && current.activePortfolioId === acknowledged.activePortfolioId
    && sameOrder(portfolioOrder, acknowledgedOrder)
  ) {
    return null
  }

  return {
    expectedRevision,
    activePortfolioId: current.activePortfolioId,
    changedPortfolios,
    portfolioOrder,
  }
}
