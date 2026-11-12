"""Stage 6.1 bank grounding / GSTIN / privacy abuse cases (offline)."""
import pytest
from tests.test_backend import case, OfflineTestExtractor
from vendorflow.pipeline import ProcessingPipeline
from vendorflow.models import CheckState, Status
from vendorflow.rules import bank_account_grounded, norm_id, duplicate_check
from vendorflow.ui_support import vendor_visible_checks


@pytest.mark.parametrize('pdftext,account,expected', [
    ('Account number:\n001234567890', '001234567890', True),
    ('Account number: 0012 3456-7890', '001234567890', True),
    ('Account number: 001234567890', '123456', False),
    ('Account number: 001234567890', '001234', False),
    ('Other reference: 001234567890', '001234567890', False),
    ('Account number: ****7890', '001234567890', False),
    ('Account number: 001234567890999', '001234567890', False),
    ('Account number: 001234567890\nOther account number: 999', '001234567890', True),
])
def test_complete_labeled_account_required(pdftext, account, expected):
    assert bank_account_grounded(account, pdftext) is expected


def test_public_duplicate_messages_do_not_expose_membership():
    vendor, _, _ = case('happy')
    match = duplicate_check(vendor, lambda *_: ['VF-PRIVATE'], 'VF-THIS')
    no_match = duplicate_check(vendor, lambda *_: [], 'VF-THIS')
    assert match.vendor_message == no_match.vendor_message
    assert match.next_action == no_match.next_action
    assert 'VF-PRIVATE' in match.admin_detail
    assert 'VF-PRIVATE' not in match.vendor_message


def test_missing_prerequisites_not_comparison_failures():
    vendor, _, _ = case('happy')
    incomplete = vendor.model_copy(update={
        'contact_email': 'invalid', 'pan': '', 'gstin': '', 'account_number': '', 'ifsc': ''
    })
    result = ProcessingPipeline(OfflineTestExtractor(), lambda *_: []).evaluate(incomplete, None, None)
    assert result.status == Status.PENDING
    assert 'valid contact email' in ' '.join(result.all_reasons)
    for code in ('PAN_GSTIN_MISMATCH', 'BANK_ACCOUNT_MISMATCH', 'BANK_IFSC_MISMATCH'):
        check = next(c for c in result.checks if c.code == code)
        assert check.state == CheckState.UNKNOWN
        assert 'differs' not in check.vendor_message.lower()
        assert 'does not match' not in check.vendor_message.lower()


def test_gstin_whitespace_canonicalization():
    for identity in [' 09abcde1234f1z5 ', '09ABCDE 1234F1Z5', '09ABCDE\t1234F1Z5']:
        assert norm_id(identity) == '09ABCDE1234F1Z5'


def test_vendor_check_rows_remove_registry():
    values = [{'rule_id': 'R12', 'admin_detail': 'VF-PRIVATE'},
              {'rule_id': 'R01', 'vendor_message': 'Correct input'}]
    assert vendor_visible_checks(values) == [values[1]]
