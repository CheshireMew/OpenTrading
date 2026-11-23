import { apiPost } from './request'

// This file is compiled but never executed. The expected errors make the generated
// API boundary fail typechecking if request bodies or path parameters become optional.
if (false) {
  // @ts-expect-error dca_simulate requires its generated request body.
  void apiPost('dca_simulate')

  // @ts-expect-error restore_research_watchlist requires its generated watchlist_id path value.
  void apiPost('restore_research_watchlist', { expectedVersion: 1 })

  void apiPost('restore_research_watchlist', { expectedVersion: 1 }, { path: { watchlist_id: 'list' } })
}
