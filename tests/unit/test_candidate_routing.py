from experiments.laya_v2.evaluate_candidate import routing_metrics


def test_escalation_reference_is_not_satisfied_by_verification():
    records = [
        {'reference_handling': 'escalate', 'acceptable_decisions': ['FRONTIER_REVIEW'],
         'candidate': {'policy_decision': 'ALLOW_WITH_VERIFICATION'}},
        {'reference_handling': 'allow', 'acceptable_decisions': ['ALLOW'],
         'candidate': {'policy_decision': 'FRONTIER_REVIEW'}},
    ]
    result = routing_metrics(records, 'candidate', 'policy_decision')
    assert result['missed_interventions'] == 0
    assert result['inadequate_handling'] == 1
    assert result['safe_interruptions'] == 1
