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
  PortfolioLedgerResponse,
  PortfolioTransactionArchiveCommand,
  PortfolioTransactionCreateCommand,
  PortfolioTransactionImportCommand,
  PortfolioTransactionImportResponse,
  PortfolioTransactionResponse,
  PortfolioTransactionUpdateCommand,
  PortfolioAnalyticsCommand,
  PortfolioAnalyticsResponse,
} from './contracts'

export const toolsApi = {
  analyzePortfolio(portfolioId: string, command: PortfolioAnalyticsCommand): Promise<PortfolioAnalyticsResponse> {
    return apiPost('analyze_portfolio', command, { path: { portfolio_id: portfolioId } })
  },
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

  getPortfolioLedger(portfolioId: string): Promise<PortfolioLedgerResponse> {
    return apiGet('get_portfolio_ledger', { path: { portfolio_id: portfolioId } })
  },

  createPortfolioTransaction(
    portfolioId: string,
    command: PortfolioTransactionCreateCommand,
  ): Promise<PortfolioTransactionResponse> {
    return apiPost('create_portfolio_transaction', command, { path: { portfolio_id: portfolioId } })
  },

  updatePortfolioTransaction(
    portfolioId: string,
    transactionId: string,
    command: PortfolioTransactionUpdateCommand,
  ): Promise<PortfolioTransactionResponse> {
    return apiPut('update_portfolio_transaction', command, { path: { portfolio_id: portfolioId, transaction_id: transactionId } })
  },

  setPortfolioTransactionArchived(
    portfolioId: string,
    transactionId: string,
    command: PortfolioTransactionArchiveCommand,
    archived: boolean,
  ): Promise<PortfolioTransactionResponse> {
    return apiPost(
      archived ? 'archive_portfolio_transaction' : 'restore_portfolio_transaction',
      command,
      { path: { portfolio_id: portfolioId, transaction_id: transactionId } },
    )
  },

  importPortfolioTransactions(
    portfolioId: string,
    command: PortfolioTransactionImportCommand,
  ): Promise<PortfolioTransactionImportResponse> {
    return apiPost('import_portfolio_transactions', command, { path: { portfolio_id: portfolioId } })
  },
}


