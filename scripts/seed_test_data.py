"""
Seed supply chain graph data.
Run inside Docker:  docker exec finance-mcp-server python tests/seed_test_data.py
Run locally:        PYTHONPATH=src NEBULA_HOST=localhost .venv/bin/python tests/seed_test_data.py
"""
import sys
sys.path.insert(0, "src")

from finance_mcp.graph.client import SecureGraphClient

with SecureGraphClient() as c:

    # -----------------------------------------------------------------------
    # 1. Company vertices
    # -----------------------------------------------------------------------

    # Semiconductor / Taiwan strait risk
    c.insert_company('TSMC', 'Taiwan Semiconductor Mfg.', 'Technology')
    c.insert_company('AAPL', 'Apple Inc.',                 'Technology')
    c.insert_company('NVDA', 'NVIDIA Corporation',         'Technology')
    c.insert_company('AMD',  'Advanced Micro Devices',     'Technology')
    c.insert_company('QCOM', 'Qualcomm Inc.',              'Technology')
    c.insert_company('INTC', 'Intel Corporation',          'Technology')
    c.insert_company('ASML', 'ASML Holding NV',            'Technology')
    c.insert_company('MSFT', 'Microsoft Corporation',      'Technology')
    c.insert_company('GOOG', 'Alphabet Inc.',              'Technology')
    c.insert_company('META', 'Meta Platforms Inc.',        'Technology')

    # EV / battery supply chain
    c.insert_company('TSLA',  'Tesla Inc.',           'Automotive')
    c.insert_company('F',     'Ford Motor Company',   'Automotive')
    c.insert_company('GM',    'General Motors',       'Automotive')
    c.insert_company('PCRHY', 'Panasonic Holdings',   'Automotive')
    c.insert_company('ALB',   'Albemarle Corp.',      'Materials')
    c.insert_company('SQM',   'SQM SA',               'Materials')

    # Energy / oil supply chain
    c.insert_company('XOM',  'ExxonMobil Corp.',   'Energy')
    c.insert_company('CVX',  'Chevron Corp.',      'Energy')
    c.insert_company('SHEL', 'Shell PLC',          'Energy')
    c.insert_company('BP',   'BP PLC',             'Energy')
    c.insert_company('HAL',  'Halliburton Co.',    'Energy')
    c.insert_company('SLB',  'SLB (Schlumberger)', 'Energy')

    print('Companies inserted')

    # -----------------------------------------------------------------------
    # 2. Commodity vertices
    # -----------------------------------------------------------------------
    c.insert_commodity('SEMICONDUCTOR', 'Semiconductors',       'Electronic Components')
    c.insert_commodity('LITHIUM',       'Lithium',              'Battery Metals')
    c.insert_commodity('COBALT',        'Cobalt',               'Battery Metals')
    c.insert_commodity('CRUDE_OIL',     'Crude Oil',            'Energy')
    c.insert_commodity('NATURAL_GAS',   'Natural Gas',          'Energy')
    c.insert_commodity('RARE_EARTH',    'Rare Earth Elements',  'Strategic Minerals')

    print('Commodities inserted')

    # -----------------------------------------------------------------------
    # 3. DEPENDS_ON edges (dependent -> supplier)
    # -----------------------------------------------------------------------
    # Big tech depends on TSMC for chip fabrication
    for src, weight in [
        ('AAPL', 0.92),   # ~90% of advanced chips from TSMC
        ('NVDA', 0.95),   # almost all GPUs fabbed at TSMC
        ('AMD',  0.90),
        ('QCOM', 0.88),
        ('INTC', 0.40),   # Intel has own fabs but also uses TSMC
        ('MSFT', 0.60),   # Azure custom silicon
        ('GOOG', 0.65),   # TPU chips
        ('META', 0.55),   # custom AI chips
        ('TSLA', 0.45),
    ]:
        c.insert_depends_on(src, 'TSMC', weight)

    # TSMC depends on ASML for EUV lithography (no ASML = no 3nm chips)
    c.insert_depends_on('TSMC', 'ASML', 0.97)

    # EV makers depend on battery suppliers
    c.insert_depends_on('TSLA', 'PCRHY', 0.70)
    c.insert_depends_on('F',    'PCRHY', 0.45)
    c.insert_depends_on('GM',   'PCRHY', 0.30)

    # Battery suppliers depend on lithium miners
    c.insert_depends_on('PCRHY', 'ALB', 0.55)
    c.insert_depends_on('PCRHY', 'SQM', 0.45)
    c.insert_depends_on('TSLA',  'ALB', 0.40)
    c.insert_depends_on('TSLA',  'SQM', 0.35)

    # Oil majors depend on oilfield services
    c.insert_depends_on('XOM',  'HAL', 0.50)
    c.insert_depends_on('XOM',  'SLB', 0.55)
    c.insert_depends_on('CVX',  'HAL', 0.45)
    c.insert_depends_on('CVX',  'SLB', 0.50)
    c.insert_depends_on('SHEL', 'SLB', 0.60)
    c.insert_depends_on('BP',   'SLB', 0.55)
    c.insert_depends_on('BP',   'HAL', 0.40)

    print('DEPENDS_ON edges inserted')

    # -----------------------------------------------------------------------
    # 4. REQUIRES edges (company -> commodity)
    # -----------------------------------------------------------------------
    c.insert_requires('TSMC',  'SEMICONDUCTOR', 1000)
    c.insert_requires('AAPL',  'RARE_EARTH',     500)
    c.insert_requires('TSLA',  'LITHIUM',        800)
    c.insert_requires('TSLA',  'COBALT',         400)
    c.insert_requires('PCRHY', 'LITHIUM',        600)
    c.insert_requires('PCRHY', 'COBALT',         300)
    c.insert_requires('F',     'LITHIUM',        300)
    c.insert_requires('GM',    'LITHIUM',        350)
    c.insert_requires('XOM',   'CRUDE_OIL',     9000)
    c.insert_requires('CVX',   'CRUDE_OIL',     7000)
    c.insert_requires('SHEL',  'CRUDE_OIL',     8000)
    c.insert_requires('SHEL',  'NATURAL_GAS',   5000)
    c.insert_requires('BP',    'CRUDE_OIL',     6000)
    c.insert_requires('BP',    'NATURAL_GAS',   4000)

    print('REQUIRES edges inserted')

    # -----------------------------------------------------------------------
    # 5. Verification
    # -----------------------------------------------------------------------
    print('\n=== Supply Chain Impact Verification ===')
    for shock, hops in [('TSMC', 2), ('ASML', 3), ('ALB', 2), ('SLB', 2)]:
        impacts = c.trace_impact(shock, hops)
        print(f'\ntrace_impact({shock}, {hops} hops) => {len(impacts)} companies affected:')
        for i in impacts:
            print(f'   {i["ticker"]:8s}  {i["name"]}')

print('\nSeed complete.')
