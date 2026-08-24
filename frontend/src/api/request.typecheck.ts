import { apiPost } from './request'

// This file is compiled but never executed. The expected errors make the generated
// API boundary fail typechecking if request bodies or path parameters become optional.
if (false) {
  // @ts-expect-error dca_simulate requires its generated request body.
  void apiPost('dca_simulate')

  // @ts-expect-error restore_portfolio requires its generated portfolio_id path value.
  void apiPost('restore_portfolio', { expectedRevision: 1 })

  void apiPost('restore_portfolio', { expectedRevision: 1 }, { path: { portfolio_id: 'core' } })
}
