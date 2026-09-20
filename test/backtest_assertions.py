"""Strict historical execution comparison across result schema versions."""
from copy import deepcopy


def assert_legacy_execution_equal(legacy, current):
    """Compare every old trading value, excluding only named schema additions.

    Research engines keep their historical output. Native event IDs, sampling
    evidence and timeline events are covered by provenance/record-store tests;
    they are not trading differences. Unrecognized fields still fail equality.
    """
    before, after = deepcopy(legacy), deepcopy(current)
    after.pop('events')
    for row in after['signals']:
        row.pop('signal_id')
    for row in after['fills']:
        row.pop('signal_id')
    for row in after['trades']:
        for field in ('entry_signal_id', 'entry_resolution_ms', 'exit_resolution_ms', 'execution_fallback_times'):
            row.pop(field)
    # Older engines serialize all current Intent dataclass defaults. Native
    # output omits disabled options; non-default research values must fail.
    for row in before['signals']:
        for field, default in (('pause_after_stop', False), ('stop_loss_confirmation', 'immediate'), ('stop_confirmation_clock', 'signal')):
            if field in row:
                assert row.pop(field) == default, field
    assert before == after
