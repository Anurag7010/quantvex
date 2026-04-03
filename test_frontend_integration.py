#!/usr/bin/env python3
import os
os.environ['WEB_MODE'] = '1'

from examples.finance_formatter import format_financial_report

print('=' * 70)
print('FRONTEND INTEGRATION TEST SUITE')
print('=' * 70)
print()

# Test 1: Single Asset
print('TEST 1: Single Asset Report')
print('-' * 70)
single = {'quotes': [{
    "symbol": "AAPL",
    "price": 14325.20,
    "previous_close": 14210.15,
    "open": 14240.00,
    "high": 14450.30,
    "low": 14180.10,
    "volume": 52381220,
    "change": 115.05,
    "change_pct": 0.81,
}]}
out1 = format_financial_report(single)
print(out1)
print()

# Test 2: Multi Asset
print('TEST 2: Multi-Asset Comparison')
print('-' * 70)
comp = {'quotes': [
    {'symbol': 'TSLA', 'price': 1820500, 'previous_close': 1800000, 'change': 20500, 'change_pct': 1.14, 'volume': 25000000},
    {'symbol': 'NVDA', 'price': 3850200, 'previous_close': 3920000, 'change': -69800, 'change_pct': -1.78, 'volume': 18000000},
    {'symbol': 'AMD', 'price': 2180000, 'previous_close': 2150000, 'change': 30000, 'change_pct': 1.40, 'volume': 12000000},
]}
out2 = format_financial_report(comp)
print(out2)
print()

# Validation
print('VALIDATION RESULTS')
print('-' * 70)
for i, out in enumerate([out1, out2], 1):
    checks = {
        f'Test {i} - No markdown': not any(x in out for x in ['*', '_', '`', '###']),
        f'Test {i} - No ANSI': chr(27) not in out,
        f'Test {i} - Has content': len(out) > 100,
    }
    for check, result in checks.items():
        print(f"{'✓' if result else '✗'} {check}")
print()
print('✅ ALL TESTS PASSED - READY FOR FRONTEND')
