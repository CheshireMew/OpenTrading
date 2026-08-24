import {
  copyPortfolioBalancePortfolio,
  createPortfolioBalancePortfolio,
} from './snapshot'
import { createDefaultPortfolioBalanceAssets } from './assets'
import type { PortfolioBalancePortfolio } from './types'

export const buildCopiedPortfolioName = (
  portfolios: PortfolioBalancePortfolio[],
  copyName: string,
) => {
  const existingNames = new Set(portfolios.map((portfolio) => portfolio.name))
  if (!existingNames.has(copyName)) return copyName

  let sequence = 2
  while (existingNames.has(`${copyName} ${sequence}`)) {
    sequence += 1
  }
  return `${copyName} ${sequence}`
}

export const createPortfolioInCollection = (
  portfolios: PortfolioBalancePortfolio[],
  name: string,
  sample = false,
) => {
  const nextPortfolio = createPortfolioBalancePortfolio({
    name,
    assets: sample ? createDefaultPortfolioBalanceAssets() : undefined,
  })
  portfolios.unshift(nextPortfolio)
  return nextPortfolio.id
}

export const copyPortfolioInCollection = (
  portfolios: PortfolioBalancePortfolio[],
  portfolioId: string,
  copyName: string,
) => {
  const index = portfolios.findIndex((portfolio) => portfolio.id === portfolioId)
  if (index < 0) return ''

  const sourcePortfolio = portfolios[index]
  const nextPortfolio = copyPortfolioBalancePortfolio(sourcePortfolio, {
    name: buildCopiedPortfolioName(portfolios, copyName),
  })
  portfolios.splice(index + 1, 0, nextPortfolio)
  return nextPortfolio.id
}

export const deletePortfolioFromCollection = (
  portfolios: PortfolioBalancePortfolio[],
  portfolioId: string,
  activePortfolioId: string,
  fallbackName: string,
) => {
  const index = portfolios.findIndex((portfolio) => portfolio.id === portfolioId)
  if (index < 0) return activePortfolioId

  portfolios.splice(index, 1)
  if (!portfolios.length) {
    const fallback = createPortfolioBalancePortfolio({ name: fallbackName })
    portfolios.push(fallback)
    return fallback.id
  }
  if (activePortfolioId === portfolioId) {
    return portfolios[0].id
  }
  return activePortfolioId
}

