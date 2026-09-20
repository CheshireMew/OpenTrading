"""Display taxonomy for known research implementations; not version evidence."""

EMA_CLOUD = {
    'trend_cloud_parameters_v4', 'trend_cloud_robustness_v1', 'trend_cloud_timeframe_v6',
    'trend_cloud_direct_v7', 'trend_cloud_width_reentry_v1', 'trend_cloud_signal_confirmation_v1',
    'trend_cloud_intrabar_confirmation_v1', 'trend_cloud_intrabar_confirmation_v2',
    'trend_cloud_intrabar_methods_v3', 'trend_cloud_intrabar_exit_v4',
    'trend_cloud_intrabar_support_v1', 'trend_cloud_reverse_after_protection_v5',
    'trend_cloud_stop_confirmation_v1',
    'trend_cloud_stop_confirmation_v2',
}


def strategy_family(identifier):
    if identifier in EMA_CLOUD:
        return 'EMA 通道'
    if identifier in {'adaptive_cloud', 'trend_cloud_comparison', 'trend_cloud_context_v3',
                      'trend_cloud_entry_v2', 'trend_cloud_experiments', 'trend_cloud_manual_v1',
                      'trend_cloud_profit_protection'}:
        return '趋势通道'
    if identifier == 'ma_cross':
        return '均线交叉'
    return None
