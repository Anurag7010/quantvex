"""
Production seed script — Phase 3 final supply-chain graph.

Adds all missing downstream oil-consumer edges so that queries like
"Iran USA war oil stocks" return meaningful cascades.

Edge semantics: (A)-[:DEPENDS_ON]->(B) means A depends on B as a supplier.
So trace_impact("XOM") finds every A such that A->...->XOM.

Run inside Docker:
    docker exec finance-mcp-server python tests/seed_production_data.py

Run locally:
    PYTHONPATH=src NEBULA_HOST=localhost .venv/bin/python tests/seed_production_data.py
"""
import sys
sys.path.insert(0, "src")

from finance_mcp.graph.client import SecureGraphClient

with SecureGraphClient() as c:

    # -----------------------------------------------------------------------
    # 1. Company vertices — full production set
    # -----------------------------------------------------------------------

    # --- Semiconductors / Taiwan risk ---
    c.insert_company('TSMC',  'Taiwan Semiconductor Mfg.',  'Technology')
    c.insert_company('AAPL',  'Apple Inc.',                  'Technology')
    c.insert_company('NVDA',  'NVIDIA Corporation',          'Technology')
    c.insert_company('AMD',   'Advanced Micro Devices',      'Technology')
    c.insert_company('QCOM',  'Qualcomm Inc.',               'Technology')
    c.insert_company('INTC',  'Intel Corporation',           'Technology')
    c.insert_company('ASML',  'ASML Holding NV',             'Technology')
    c.insert_company('MSFT',  'Microsoft Corporation',       'Technology')
    c.insert_company('GOOG',  'Alphabet Inc.',               'Technology')
    c.insert_company('META',  'Meta Platforms Inc.',         'Technology')
    c.insert_company('AMZN',  'Amazon.com Inc.',             'Technology')

    # --- EV / battery supply chain ---
    c.insert_company('TSLA',  'Tesla Inc.',            'Automotive')
    c.insert_company('F',     'Ford Motor Company',    'Automotive')
    c.insert_company('GM',    'General Motors',        'Automotive')
    c.insert_company('PCRHY', 'Panasonic Holdings',    'Automotive')
    c.insert_company('ALB',   'Albemarle Corp.',       'Materials')
    c.insert_company('SQM',   'SQM SA',                'Materials')

    # --- Energy producers ---
    c.insert_company('XOM',  'ExxonMobil Corp.',    'Energy')
    c.insert_company('CVX',  'Chevron Corp.',       'Energy')
    c.insert_company('SHEL', 'Shell PLC',           'Energy')
    c.insert_company('BP',   'BP PLC',              'Energy')
    c.insert_company('HAL',  'Halliburton Co.',     'Energy')
    c.insert_company('SLB',  'SLB (Schlumberger)',  'Energy')

    # --- Oil consumers: Airlines (heavy jet-fuel dependency) ---
    c.insert_company('DAL', 'Delta Air Lines',        'Airlines')
    c.insert_company('UAL', 'United Airlines',        'Airlines')
    c.insert_company('LUV', 'Southwest Airlines',     'Airlines')
    c.insert_company('AAL', 'American Airlines',      'Airlines')

    # --- Oil consumers: Shipping & Logistics ---
    c.insert_company('FDX', 'FedEx Corporation',  'Logistics')
    c.insert_company('UPS', 'United Parcel Service', 'Logistics')
    c.insert_company('MAERSK', 'A.P. Moller-Maersk', 'Shipping')

    # --- Oil consumers: Petrochemicals / Plastics ---
    c.insert_company('DOW',  'Dow Inc.',               'Materials')
    c.insert_company('LYB',  'LyondellBasell Industries', 'Materials')
    c.insert_company('DD',   'DuPont de Nemours',      'Materials')

    # --- Oil consumers: Heavy industry / Aerospace ---
    c.insert_company('BA',   'Boeing Company',        'Aerospace')
    c.insert_company('CAT',  'Caterpillar Inc.',      'Industrials')
    c.insert_company('DE',   'Deere & Company',       'Industrials')

    print("Companies inserted")

    # -----------------------------------------------------------------------
    # 2. Commodity vertices
    # -----------------------------------------------------------------------
    c.insert_commodity('SEMICONDUCTOR', 'Semiconductors',      'Electronic Components')
    c.insert_commodity('LITHIUM',       'Lithium',             'Battery Metals')
    c.insert_commodity('COBALT',        'Cobalt',              'Battery Metals')
    c.insert_commodity('CRUDE_OIL',     'Crude Oil',           'Energy')
    c.insert_commodity('NATURAL_GAS',   'Natural Gas',         'Energy')
    c.insert_commodity('RARE_EARTH',    'Rare Earth Elements', 'Strategic Minerals')
    c.insert_commodity('JET_FUEL',      'Jet Fuel',            'Energy')

    print("Commodities inserted")

    # -----------------------------------------------------------------------
    # 3. DEPENDS_ON edges
    #
    # Edge direction: (consumer) -[:DEPENDS_ON]-> (supplier)
    # trace_impact("X") returns every consumer that transitively depends on X
    # -----------------------------------------------------------------------

    # --- Big Tech depends on TSMC for chip fabrication ---
    for src, weight in [
        ('AAPL', 0.92),
        ('NVDA', 0.95),
        ('AMD',  0.90),
        ('QCOM', 0.88),
        ('INTC', 0.40),
        ('MSFT', 0.60),
        ('GOOG', 0.65),
        ('META', 0.55),
        ('TSLA', 0.45),
        ('AMZN', 0.50),
    ]:
        c.insert_depends_on(src, 'TSMC', weight)

    # TSMC depends on ASML for EUV lithography
    c.insert_depends_on('TSMC', 'ASML', 0.97)

    # --- EV makers depend on battery cell suppliers ---
    c.insert_depends_on('TSLA', 'PCRHY', 0.70)
    c.insert_depends_on('F',    'PCRHY', 0.45)
    c.insert_depends_on('GM',   'PCRHY', 0.30)

    # Battery suppliers depend on lithium miners
    c.insert_depends_on('PCRHY', 'ALB', 0.55)
    c.insert_depends_on('PCRHY', 'SQM', 0.45)
    c.insert_depends_on('TSLA',  'ALB', 0.40)
    c.insert_depends_on('TSLA',  'SQM', 0.35)
    c.insert_depends_on('F',     'ALB', 0.25)
    c.insert_depends_on('GM',    'ALB', 0.25)

    # --- Oil majors depend on oilfield services companies ---
    c.insert_depends_on('XOM',  'HAL', 0.50)
    c.insert_depends_on('XOM',  'SLB', 0.55)
    c.insert_depends_on('CVX',  'HAL', 0.45)
    c.insert_depends_on('CVX',  'SLB', 0.50)
    c.insert_depends_on('SHEL', 'SLB', 0.60)
    c.insert_depends_on('BP',   'SLB', 0.55)
    c.insert_depends_on('BP',   'HAL', 0.40)

    # --- Airlines depend on oil majors for jet fuel supply ---
    # This is the key missing set: makes oil-war disruptions cascade to airlines
    for airline, weight in [
        ('DAL', 0.85),
        ('UAL', 0.82),
        ('LUV', 0.88),
        ('AAL', 0.84),
    ]:
        c.insert_depends_on(airline, 'XOM',  weight * 0.40)
        c.insert_depends_on(airline, 'CVX',  weight * 0.35)
        c.insert_depends_on(airline, 'SHEL', weight * 0.15)
        c.insert_depends_on(airline, 'BP',   weight * 0.10)

    # --- Logistics depends on oil majors for diesel/bunker fuel ---
    c.insert_depends_on('FDX',   'XOM',  0.45)
    c.insert_depends_on('FDX',   'CVX',  0.35)
    c.insert_depends_on('UPS',   'XOM',  0.40)
    c.insert_depends_on('UPS',   'CVX',  0.35)
    c.insert_depends_on('MAERSK', 'XOM',  0.50)
    c.insert_depends_on('MAERSK', 'SHEL', 0.50)

    # --- Petrochemicals depend on oil majors for feedstock ---
    c.insert_depends_on('DOW',  'XOM',  0.55)
    c.insert_depends_on('DOW',  'SHEL', 0.30)
    c.insert_depends_on('LYB',  'XOM',  0.60)
    c.insert_depends_on('LYB',  'CVX',  0.40)
    c.insert_depends_on('DD',   'XOM',  0.35)
    c.insert_depends_on('DD',   'CVX',  0.30)

    # --- Aerospace / heavy industry depend on oil for production energy ---
    c.insert_depends_on('BA',  'XOM', 0.30)
    c.insert_depends_on('BA',  'CVX', 0.25)
    c.insert_depends_on('CAT', 'XOM', 0.35)
    c.insert_depends_on('DE',  'XOM', 0.30)

    # --- Airlines also depend on Boeing for aircraft ---
    c.insert_depends_on('DAL', 'BA', 0.60)
    c.insert_depends_on('UAL', 'BA', 0.55)
    c.insert_depends_on('AAL', 'BA', 0.65)
    c.insert_depends_on('LUV', 'BA', 0.95)  # Southwest is nearly all-Boeing fleet

    print("DEPENDS_ON edges inserted")

    # -----------------------------------------------------------------------
    # 4. REQUIRES edges (company -> commodity they consume)
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
    c.insert_requires('DAL',   'JET_FUEL',      9500)
    c.insert_requires('UAL',   'JET_FUEL',      8800)
    c.insert_requires('LUV',   'JET_FUEL',      7200)
    c.insert_requires('AAL',   'JET_FUEL',      9200)
    c.insert_requires('DOW',   'CRUDE_OIL',     6000)
    c.insert_requires('LYB',   'CRUDE_OIL',     5000)
    c.insert_requires('BA',    'RARE_EARTH',     800)

    print("REQUIRES edges inserted")

    # -----------------------------------------------------------------------
    # 5. Verification — trace all key supply chain anchors
    # -----------------------------------------------------------------------
    print('\n' + '='*60)
    print('SUPPLY CHAIN VERIFICATION')
    print('='*60)

    test_cases = [
        ('TSMC',  2, 'Taiwan chip shock'),
        ('ASML',  3, 'Lithography equipment ban'),
        ('XOM',   2, 'ExxonMobil oil disruption'),
        ('CVX',   2, 'Chevron oil disruption'),
        ('ALB',   2, 'Lithium shortage'),
        ('SLB',   2, 'Oilfield services disruption'),
        ('BA',    2, 'Boeing production halt'),
    ]

    for ticker, hops, scenario in test_cases:
        impacts = c.trace_impact(ticker, hops)
        print(f'\ntrace_impact("{ticker}", {hops} hops) [{scenario}]')
        print(f'  => {len(impacts)} companies downstream:')
        for co in impacts:
            print(f'     {co["ticker"]:8s}  {co["name"]}  [{co["sector"]}]')

print('\nSEED COMPLETE')
