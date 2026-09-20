from scripts.verify_pine_contract import verify


def test_pine_delivery_identity_labels_and_shared_event_fixtures():
    result = verify()
    assert result['ok'], [v for v in result['checks'] if not v['passed']]
    assert result['pine_compilation'] == 'not_verified'
    assert result['pine_runtime_event_parity'] == 'not_verified'
    assert len(result['fixtures']) == 5
