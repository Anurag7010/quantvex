#!/usr/bin/env python3
import os
os.environ['WEB_MODE'] = '1'

from examples.finance_formatter import format_financial_report

comp = {'quotes': [
    {'symbol': 'AAL', 'price': 1150.42, 'previous_close': 1125.00, 'change': 25.42, 'change_pct': 2.26, 'volume': 30211200},
    {'symbol': 'DAL', 'price': 4280.10, 'previous_close': 4300.00, 'change': -19.90, 'change_pct': -0.46, 'volume': 19834000},
]}
out = format_financial_report(comp)

# Validation checks
checks = {
    'No asterisks': '*' not in out,
    'No underscores': '_' not in out,
    'No backticks': '`' not in out,
    'No ANSI codes': chr(27) not in out,
    'Uses bullets': '•' in out,
    'Table present': 'Asset' in out and 'Price' in out,
}

print('✅ FRONTEND OUTPUT VALIDATION')
print()
for check, result in checks.items():
    status = '✓' if result else '✗'
    print(f'{status} {check}')
print()
print('═' * 70)
print('SAMPLE OUTPUT:')
print('═' * 70)
print(out)
