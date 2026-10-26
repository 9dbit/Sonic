"""SONIC voice 429 diagnostic boundaries. Provider data is untrusted."""
from sonic.provider_diagnostics import classify_provider_error, browser_error_description


def test_prepaid_credit_exhausted_is_distinct_from_transient_rate_limit():
    result = classify_provider_error(
        429,
        {'error': {'type': 'insufficient_quota', 'code': 'credit_balance_exhausted',
                   'message': 'UNSAFE_PRIVATE_PROVIDER_BODY'}},
        {'x-request-id': 'req_abc0123456789xyz', 'retry-after': '20'},
    )
    assert result['code'] == 'credit_balance_exhausted'
    assert result['request_id'] == 'req_abc0123456789xyz'
    assert result['retry_after_seconds'] == 20
    description = browser_error_description(result)
    assert 'credit_balance_exhausted' in description
    assert 'UNSAFE_PRIVATE_PROVIDER_BODY' not in description
    assert 'Retry-After' not in description


def test_rate_limit_advises_pause_without_expensive_retry_loop():
    result = classify_provider_error(429, {'error': {'type': 'rate_limit_error', 'code': None}},
                                     {'retry-after': '12'})
    assert result['code'] == 'rate_limit_exceeded'
    assert result['retry_after_seconds'] == 12
    assert 'Retry-After: 12 detik' in browser_error_description(result)


def test_project_and_organization_spend_codes_are_distinct():
    codes = ['organization_usage_limit_exceeded', 'organization_spend_limit_exceeded',
             'project_spend_limit_exceeded']
    assert len(set(classify_provider_error(429, {'error': {'code': code}})['code']
                   for code in codes)) == len(codes)


def test_unknown_error_cannot_reflect_provider_content_into_browser():
    malicious = '<script>window.location="https://attacker.invalid"</script>'
    result = classify_provider_error(429, {'error': {'code': malicious,
                                                    'type': malicious,
                                                    'message': 'private audio ' + malicious}},
                                     {'x-request-id': 'secret_data\r\nInjected: true',
                                      'retry-after': '99999999'})
    assert result['code'] == 'unclassified_429'
    assert result['request_id'] is None
    assert result['retry_after_seconds'] is None
    description = browser_error_description(result)
    assert '<script>' not in description
    assert 'private audio' not in description


def test_malformed_body_and_headers_remain_bounded():
    assert classify_provider_error(429, None)['code'] == 'unclassified_429'
    assert classify_provider_error(403, 'not json')['code'] == 'unclassified_provider_error'
    assert len(browser_error_description(classify_provider_error(
        429, {'error': ['error', {'code': 'project_spend_limit_exceeded'}]}))) < 601


def test_provider_message_is_not_used_to_guess_billing_code():
    result = classify_provider_error(429,
        {'error': {'code': 'unknown_new_code', 'message': 'You exceeded the balance for a different org'}})
    assert result['code'] == 'unclassified_429'
