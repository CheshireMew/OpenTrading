import { defineStore } from 'pinia'
import { marketInsightApi } from './api'
import type { DliLiquidityResponse } from './contracts'
import { MARKET_CACHE_TTL_MS } from './cacheTypes'
import { createResourceLoader, createResourceState, isResourceLoading, readResource, readResourceError, type ResourceState } from './resourceCache'

interface MacroLiquidityState {
  resources: ResourceState<DliLiquidityResponse>
}

const dliLiquidityResource = createResourceLoader<DliLiquidityResponse>()
const dliLiquidityKey = (days: number, changeDays: number) => `days:${days}:change_days:${changeDays}`

export const useMacroLiquidityStore = defineStore('macroLiquidity', {
  state: (): MacroLiquidityState => ({
    resources: createResourceState<DliLiquidityResponse>(),
  }),

  actions: {
    getDliLiquidityCacheKey(days: number, changeDays: number = 30): string {
      return dliLiquidityKey(days, changeDays)
    },

    readDliLiquidity(days: number, changeDays: number = 30): DliLiquidityResponse | null {
      return readResource(this.resources, this.getDliLiquidityCacheKey(days, changeDays))
    },

    isDliLiquidityLoading(days: number, changeDays: number = 30): boolean {
      return isResourceLoading(this.resources, this.getDliLiquidityCacheKey(days, changeDays))
    },

    getDliLiquidityError(days: number, changeDays: number = 30): string {
      return readResourceError(this.resources, this.getDliLiquidityCacheKey(days, changeDays))
    },

    async getDliLiquidity(
      days: number,
      changeDays: number = 30,
      options: { force?: boolean } = {},
    ): Promise<DliLiquidityResponse | null> {
      const key = this.getDliLiquidityCacheKey(days, changeDays)
      return dliLiquidityResource.load(this.resources, {
        key,
        ttlMs: MARKET_CACHE_TTL_MS.macroLiquidity,
        force: options.force,
        load: () => marketInsightApi.getDliLiquidity({ days, change_days: changeDays }),
        errorKey: 'common.macroLiquidityLoadFailed',
        onError: (error) => {
          console.error('DLI liquidity fetch failed', error)
        }
      })
    },
  },
})
