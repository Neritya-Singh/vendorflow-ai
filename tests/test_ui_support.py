"""Pure UI helper tests; no Streamlit server, Gemini API or Supabase access."""
from vendorflow.ui_support import (
    completed_counts, comparison_rows, display_status,
    mask_sensitive, selected_reasons, stage_rows, vendor_visible_checks,
)


def test_status_labels_not_color_only():
    assert 'Approved' in display_status('APPROVED')
    assert 'Pending Review' in display_status('PENDING')
    assert 'Rejected' in display_status('REJECTED')


def test_sensitive_bank_numbers_are_masked():
    assert mask_sensitive('000123456789') == '••••••••6789'
    assert mask_sensitive('') == 'Not found'
    assert mask_sensitive('23') == '••'
    rows = comparison_rows({'account_number':'000123456789'}, {'bank': {'account_number': '009876543210'}})
    assert '000123456789' not in str(rows)
    assert '009876543210' not in str(rows)
    assert '••' in str(rows)


def test_manual_action_overrides_stale_run_explanation():
    application = {'decision_source': 'MANUAL', 'current_status': 'REJECTED'}
    run = {'reasons_json': ['Old missing PAN warning']}
    review = {'action': 'REJECT', 'reason': 'Confirmed duplicate registration'}
    reasons = selected_reasons(application, [run], [review])
    assert 'Confirmed duplicate' in reasons[0]
    assert 'Old missing PAN' not in reasons[0]


def test_automatic_reason_comes_from_actual_saved_run():
    reasons = selected_reasons({'decision_source': 'AUTOMATED'},
                               [{'reasons_json':['PAN and GSTIN differ']}], [])
    assert reasons == ['PAN and GSTIN differ']


def test_metrics_use_saved_results_only():
    apps = [{'current_status':'APPROVED'}, {'current_status':'PENDING'},
            {'current_status':'REJECTED'}, {'current_status':'PENDING'}]
    runs = [{'elapsed_ms': 1000}, {'elapsed_ms': 3000}]
    kpis = completed_counts(apps, runs)
    assert (kpis['total'], kpis['approved'], kpis['pending'], kpis['rejected']) == (4, 1, 2, 1)
    assert kpis['run_count'] == 2 and kpis['mean_seconds'] == 2.0
    assert completed_counts([],[])['mean_seconds'] is None


def test_stage_timeline_discards_start_entries_but_preserves_failure():
    events = [
        {'stage_id':'S3', 'label':'Extract', 'event':'STARTED'},
        {'stage_id':'S3', 'label':'Extract', 'event':'FAILED', 'note':'AI unavailable'},
        {'stage_id':'S7', 'label':'Decide', 'event':'COMPLETED', 'note':'PENDING'},
    ]
    timeline = stage_rows(events)
    assert len(timeline) == 2
    assert timeline[0]['Result'].endswith('FAILED')
    assert timeline[1]['Details'] == 'PENDING'


def test_vendor_check_details_do_not_reveal_registry():
    checks = [{"rule_id":"R12","admin_detail":"VF-PRIVATE"},{"rule_id":"R01","vendor_message":"Correct claim"}]
    assert vendor_visible_checks(checks) == [checks[1]]
    result = selected_reasons({"decision_source":"MANUAL","current_status":"PENDING"}, [],
                [{"action":"REQUEST_CORRECTION","reason":"Duplicate registration VF-OTHER"}], audience="vendor")
    assert "duplicate" not in str(result).lower() and "vf-other" not in str(result).lower()
