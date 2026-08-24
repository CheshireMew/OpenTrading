import { apiGet, apiPatch, apiPost, apiPut } from '@/api/request'
import type {
  DCAResponse,
  ComparePairsCommand,
  PairCompareToolResponse,
  SimulateDcaCommand,
  ToolsPageContractResponse,
  PortfolioCollectionImportCommand,
  PortfolioCollectionChangeCommand,
  PortfolioCollectionResponse,
  PortfolioCollectionSaveCommand,
  PortfolioDeletedPage,
  PortfolioExportDocument,
  PortfolioSimulationResultCommand,
  PortfolioSimulationResultResponse,
  PortfolioRestoreCommand,
} from './contracts'

export const toolsApi = {
  getContract(): Promise<ToolsPageContractResponse> {
    return apiGet('get_tools_contract')
  },

  runSimulation(config: SimulateDcaCommand): Promise<DCAResponse> {
    return apiPost('dca_simulate', config)
  },

  comparePairs(params: ComparePairsCommand): Promise<PairCompareToolResponse> {
    return apiPost('compare_pairs', params)
  },

  getPortfolioCollection(): Promise<PortfolioCollectionResponse> {
    return apiGet('get_portfolio_collection')
  },

  savePortfolioCollection(command: PortfolioCollectionSaveCommand): Promise<PortfolioCollectionResponse> {
    return apiPut('save_portfolio_collection', command)
  },

  changePortfolioCollection(command: PortfolioCollectionChangeCommand): Promise<PortfolioCollectionResponse> {
    return apiPatch('change_portfolio_collection', command)
  },

  listDeletedPortfolios(offset = 0, limit = 20): Promise<PortfolioDeletedPage> {
    return apiGet('list_deleted_portfolios', { query: { offset, limit } })
  },

  exportPortfolioCollection(): Promise<PortfolioExportDocument> {
    return apiGet('export_portfolio_collection')
  },

  importPortfolioCollection(command: PortfolioCollectionImportCommand): Promise<PortfolioCollectionResponse> {
    return apiPost('import_portfolio_collection', command)
  },

  restorePortfolio(portfolioId: string, command: PortfolioRestoreCommand): Promise<PortfolioCollectionResponse> {
    return apiPost('restore_portfolio', command, { path: { portfolio_id: portfolioId } })
  },

  getPortfolioSimulation(portfolioId: string): Promise<PortfolioSimulationResultResponse> {
    return apiGet('get_portfolio_simulation', { path: { portfolio_id: portfolioId } })
  },

  savePortfolioSimulation(
    portfolioId: string,
    command: PortfolioSimulationResultCommand,
  ): Promise<PortfolioSimulationResultResponse> {
    return apiPut('save_portfolio_simulation', command, { path: { portfolio_id: portfolioId } })
  },
}


