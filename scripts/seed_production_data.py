"""
Production seed script for the QuantVex supply-chain graph (Memgraph).

Run locally:
    PYTHONPATH=src python3 scripts/seed_production_data.py

Dry run:
    python3 scripts/seed_production_data.py --dry-run

Prerequisites:
    cd docker && docker-compose -f memgraph-docker-compose.yml up -d
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finance_mcp.graph.client import GraphClient

Company = tuple[str, str, str]
Commodity = tuple[str, str, str]
DependsOnEdge = tuple[str, str, float]
RequiresEdge = tuple[str, str, int]
HistoricalEvent = tuple[str, str, str, tuple[str, ...]]

COMPANIES: tuple[Company, ...] = (
    ("AAPL", "Apple Inc.", "Technology"),
    ("MSFT", "Microsoft Corporation", "Technology"),
    ("NVDA", "NVIDIA Corporation", "Technology"),
    ("GOOGL", "Alphabet Inc.", "Technology"),
    ("META", "Meta Platforms Inc.", "Technology"),
    ("AVGO", "Broadcom Inc.", "Technology"),
    ("ORCL", "Oracle Corporation", "Technology"),
    ("AMD", "Advanced Micro Devices", "Technology"),
    ("QCOM", "Qualcomm Inc.", "Technology"),
    ("TXN", "Texas Instruments", "Technology"),
    ("AMAT", "Applied Materials", "Technology"),
    ("MU", "Micron Technology", "Technology"),
    ("INTC", "Intel Corporation", "Technology"),
    ("TSMC", "Taiwan Semiconductor Mfg", "Technology"),
    ("ASML", "ASML Holding", "Technology"),
    ("LRCX", "Lam Research", "Technology"),
    ("KLAC", "KLA Corporation", "Technology"),
    ("AMZN", "Amazon.com Inc.", "Consumer Discretionary"),
    ("TSLA", "Tesla Inc.", "Consumer Discretionary"),
    ("HD", "Home Depot", "Consumer Discretionary"),
    ("NKE", "Nike Inc.", "Consumer Discretionary"),
    ("MCD", "McDonald's Corporation", "Consumer Discretionary"),
    ("SBUX", "Starbucks Corporation", "Consumer Discretionary"),
    ("TGT", "Target Corporation", "Consumer Discretionary"),
    ("LLY", "Eli Lilly and Company", "Healthcare"),
    ("UNH", "UnitedHealth Group", "Healthcare"),
    ("JNJ", "Johnson & Johnson", "Healthcare"),
    ("ABBV", "AbbVie Inc.", "Healthcare"),
    ("MRK", "Merck & Co.", "Healthcare"),
    ("PFE", "Pfizer Inc.", "Healthcare"),
    ("TMO", "Thermo Fisher Scientific", "Healthcare"),
    ("DHR", "Danaher Corporation", "Healthcare"),
    ("BRK_B", "Berkshire Hathaway", "Financials"),
    ("JPM", "JPMorgan Chase", "Financials"),
    ("V", "Visa Inc.", "Financials"),
    ("MA", "Mastercard Inc.", "Financials"),
    ("BAC", "Bank of America", "Financials"),
    ("GS", "Goldman Sachs", "Financials"),
    ("MS", "Morgan Stanley", "Financials"),
    ("BLK", "BlackRock Inc.", "Financials"),
    ("XOM", "ExxonMobil Corporation", "Energy"),
    ("CVX", "Chevron Corporation", "Energy"),
    ("DAL", "Delta Air Lines", "Industrials"),
    ("UAL", "United Airlines Holdings", "Industrials"),
    ("LUV", "Southwest Airlines", "Industrials"),
    ("FDX", "FedEx Corporation", "Industrials"),
    ("UPS", "United Parcel Service", "Industrials"),
    ("COP", "ConocoPhillips", "Energy"),
    ("SLB", "SLB (Schlumberger)", "Energy"),
    ("CAT", "Caterpillar Inc.", "Industrials"),
    ("BA", "Boeing Company", "Industrials"),
    ("GE", "GE Aerospace", "Industrials"),
    ("HON", "Honeywell International", "Industrials"),
    ("RTX", "RTX Corporation", "Industrials"),
    ("DE", "Deere & Company", "Industrials"),
    ("LMT", "Lockheed Martin", "Industrials"),
    ("FCX", "Freeport-McMoRan", "Materials"),
    ("PG", "Procter & Gamble", "Consumer Staples"),
    ("KO", "Coca-Cola Company", "Consumer Staples"),
    ("PEP", "PepsiCo Inc.", "Consumer Staples"),
    ("WMT", "Walmart Inc.", "Consumer Staples"),
    ("COST", "Costco Wholesale", "Consumer Staples"),
)

COMMODITIES: tuple[Commodity, ...] = (
    ("CRUDE_OIL", "Crude Oil (WTI)", "Energy"),
    ("NATURAL_GAS", "Natural Gas", "Energy"),
    ("COAL", "Thermal Coal", "Energy"),
    ("SEMICONDUCTOR_WAFER", "Semiconductor Wafers", "Electronics"),
    ("LITHIUM", "Lithium Carbonate", "Metals & Mining"),
    ("COBALT", "Cobalt", "Metals & Mining"),
    ("COPPER", "Copper", "Metals & Mining"),
    ("RARE_EARTH", "Rare Earth Elements", "Metals & Mining"),
    ("ALUMINUM", "Aluminum", "Metals & Mining"),
    ("STEEL", "Steel (HRC)", "Metals & Mining"),
    ("CORN", "Corn", "Agriculture"),
    ("WHEAT", "Wheat", "Agriculture"),
    ("SOYBEANS", "Soybeans", "Agriculture"),
    ("COFFEE", "Coffee (Arabica)", "Agriculture"),
    ("SUGAR", "Raw Sugar", "Agriculture"),
    ("PALM_OIL", "Palm Oil", "Agriculture"),
    ("SHIPPING_CONTAINERS", "Shipping Container Capacity", "Logistics"),
    ("SEMICONDUCTOR_CHIPS", "Advanced Logic Chips", "Electronics"),
    ("SILICON", "Polysilicon", "Electronics"),
    ("NEON_GAS", "Neon Gas", "Electronics"),
)

DEPENDS_ON_EDGES: tuple[DependsOnEdge, ...] = (
    ("AAPL", "TSMC", 0.95), ("AAPL", "QCOM", 0.60), ("AAPL", "AVGO", 0.55), ("AAPL", "MU", 0.45),
    ("NVDA", "TSMC", 0.98), ("NVDA", "ASML", 0.70), ("NVDA", "MU", 0.50), ("NVDA", "LRCX", 0.40),
    ("AMD", "TSMC", 0.95), ("AMD", "MU", 0.45), ("AMD", "ASML", 0.60),
    ("INTC", "ASML", 0.90), ("INTC", "LRCX", 0.55), ("INTC", "KLAC", 0.50), ("INTC", "AMAT", 0.55),
    ("TSMC", "ASML", 0.95), ("TSMC", "AMAT", 0.70), ("TSMC", "LRCX", 0.65), ("TSMC", "KLAC", 0.60),
    ("QCOM", "TSMC", 0.90), ("QCOM", "ASML", 0.55),
    ("TSLA", "TSMC", 0.50), ("TSLA", "NVDA", 0.35), ("TSLA", "FCX", 0.60), ("TSLA", "AMZN", 0.20),
    ("AMZN", "NVDA", 0.65), ("AMZN", "TSMC", 0.45), ("AMZN", "QCOM", 0.30),
    ("MSFT", "NVDA", 0.70), ("MSFT", "AMD", 0.40), ("MSFT", "TSMC", 0.40), ("MSFT", "AMZN", 0.15),
    ("META", "NVDA", 0.80), ("META", "TSMC", 0.45), ("META", "AMD", 0.35),
    ("GOOGL", "TSMC", 0.55), ("GOOGL", "NVDA", 0.60), ("GOOGL", "ASML", 0.40),
    ("BA", "GE", 0.80), ("BA", "HON", 0.65), ("BA", "RTX", 0.70), ("BA", "DE", 0.20), ("BA", "CAT", 0.25),
    ("LMT", "RTX", 0.55), ("LMT", "HON", 0.50), ("LMT", "GE", 0.45),
    ("XOM", "SLB", 0.70), ("CVX", "SLB", 0.65), ("COP", "SLB", 0.60),
    ("DAL", "XOM", 0.85), ("UAL", "XOM", 0.82), ("LUV", "XOM", 0.78),
    ("FDX", "XOM", 0.65), ("UPS", "XOM", 0.60),
    ("PFE", "TMO", 0.60), ("ABBV", "TMO", 0.50), ("MRK", "TMO", 0.55), ("LLY", "TMO", 0.65), ("LLY", "DHR", 0.55),
    ("WMT", "AMZN", 0.10), ("TGT", "AMZN", 0.08), ("NKE", "TSMC", 0.05), ("MCD", "DE", 0.10),
    ("JPM", "MSFT", 0.45), ("GS", "MSFT", 0.40), ("MS", "MSFT", 0.40), ("BLK", "MSFT", 0.35), ("V", "MSFT", 0.30), ("MA", "MSFT", 0.30),
)

REQUIRES_EDGES: tuple[RequiresEdge, ...] = (
    ("TSMC", "SILICON", 5000), ("TSMC", "NEON_GAS", 200), ("TSMC", "SEMICONDUCTOR_WAFER", 8000),
    ("NVDA", "SEMICONDUCTOR_CHIPS", 3000), ("AMD", "SEMICONDUCTOR_CHIPS", 1500),
    ("INTC", "SILICON", 2000), ("INTC", "NEON_GAS", 100), ("AMAT", "SILICON", 500), ("ASML", "RARE_EARTH", 50),
    ("TSLA", "LITHIUM", 2000), ("TSLA", "COBALT", 300), ("TSLA", "COPPER", 5000), ("TSLA", "ALUMINUM", 8000), ("TSLA", "RARE_EARTH", 200), ("TSLA", "CRUDE_OIL", 0),
    ("CAT", "STEEL", 50000), ("CAT", "COPPER", 2000), ("BA", "ALUMINUM", 30000), ("BA", "STEEL", 10000), ("DE", "STEEL", 20000),
    ("GE", "RARE_EARTH", 100), ("GE", "ALUMINUM", 5000), ("RTX", "RARE_EARTH", 80), ("RTX", "ALUMINUM", 4000),
    ("LMT", "ALUMINUM", 6000), ("LMT", "RARE_EARTH", 120), ("FCX", "COAL", 1000),
    ("XOM", "CRUDE_OIL", 500000), ("CVX", "CRUDE_OIL", 300000), ("COP", "NATURAL_GAS", 200000), ("SLB", "STEEL", 5000),
    ("MCD", "CORN", 10000), ("MCD", "WHEAT", 5000), ("MCD", "PALM_OIL", 2000),
    ("SBUX", "COFFEE", 5000), ("SBUX", "SUGAR", 1000), ("KO", "CORN", 20000), ("KO", "SUGAR", 15000),
    ("PEP", "CORN", 25000), ("PEP", "SUGAR", 12000), ("WMT", "SHIPPING_CONTAINERS", 100000),
    ("AMZN", "SHIPPING_CONTAINERS", 80000), ("COST", "SHIPPING_CONTAINERS", 40000), ("NKE", "SHIPPING_CONTAINERS", 15000),
    ("PG", "PALM_OIL", 8000), ("PG", "ALUMINUM", 2000),
    ("PFE", "NATURAL_GAS", 500), ("ABBV", "NATURAL_GAS", 300), ("LLY", "NATURAL_GAS", 400),
    ("MSFT", "NATURAL_GAS", 5000), ("AMZN", "NATURAL_GAS", 8000), ("GOOGL", "NATURAL_GAS", 4000),
    ("JPM", "CRUDE_OIL", 0),
)

HISTORICAL_EVENTS: tuple[HistoricalEvent, ...] = (
    ("EVT_TAIWAN_STRAIT_2024", "Taiwan Strait military tension escalation", "critical", ("TSMC", "AAPL", "NVDA", "AMD", "QCOM", "ASML")),
    ("EVT_OPEC_CUT_2024", "OPEC+ production cut announcement", "high", ("CRUDE_OIL", "XOM", "CVX", "COP", "TSLA", "NKE")),
    ("EVT_SUEZ_BLOCKAGE_2024", "Red Sea shipping disruption", "high", ("SHIPPING_CONTAINERS", "AMZN", "WMT", "NKE", "COST")),
    ("EVT_RARE_EARTH_CHINA_2024", "China rare earth export restrictions", "critical", ("RARE_EARTH", "TSLA", "GE", "RTX", "LMT", "NVDA")),
    ("EVT_LITHIUM_SURPLUS_2024", "Lithium price crash - oversupply", "medium", ("LITHIUM", "TSLA", "MU")),
    ("EVT_AI_CHIP_EXPORT_BAN", "US AI chip export controls tightened", "high", ("NVDA", "AMD", "AMAT", "LRCX", "KLAC")),
    ("EVT_NEON_UKRAINE_2022", "Ukraine conflict disrupts neon gas supply", "high", ("NEON_GAS", "TSMC", "INTC", "ASML")),
    ("EVT_NATURAL_GAS_EU_2022", "European natural gas supply crisis", "high", ("NATURAL_GAS", "MSFT", "AMZN", "PFE")),
)

SEVERITY_SCORE = {"medium": 5, "high": 8, "critical": 10}


def _count_unique_pairs(edges: Iterable[tuple[str, str, object]]) -> int:
    return len({(src, dst) for src, dst, _ in edges})


def print_dry_run() -> None:
    impact_edges = sum(len(event[3]) for event in HISTORICAL_EVENTS)
    print("DRY RUN - no graph writes")
    print(f"Company count: {len(COMPANIES)}")
    print(f"Commodity count: {len(COMMODITIES)}")
    print(f"DEPENDS_ON edge count: {_count_unique_pairs(DEPENDS_ON_EDGES)}")
    print(f"REQUIRES edge count: {_count_unique_pairs(REQUIRES_EDGES)}")
    print(f"Event count: {len(HISTORICAL_EVENTS)}")
    print(f"IMPACTS edge count: {impact_edges}")


def create_companies(client: GraphClient) -> None:
    for ticker, name, sector in COMPANIES:
        client.insert_company(ticker, name, sector)
    print(f"Companies upserted: {len(COMPANIES)}")


def create_commodities(client: GraphClient) -> None:
    for commodity_id, name, category in COMMODITIES:
        client.insert_commodity(commodity_id, name, category)
    print(f"Commodities upserted: {len(COMMODITIES)}")


def create_depends_on_edges(client: GraphClient) -> None:
    for src, dst, weight in DEPENDS_ON_EDGES:
        client.insert_depends_on(src, dst, weight)
    print(f"DEPENDS_ON edges inserted: {_count_unique_pairs(DEPENDS_ON_EDGES)}")


def create_requires_edges(client: GraphClient) -> None:
    for src, dst, volume in REQUIRES_EDGES:
        client.insert_requires(src, dst, volume)
    print(f"REQUIRES edges inserted: {_count_unique_pairs(REQUIRES_EDGES)}")


def create_historical_events(client: GraphClient) -> None:
    impact_count = 0
    for event_id, description, severity, impacted_entities in HISTORICAL_EVENTS:
        client.upsert_event(event_id, description, SEVERITY_SCORE[severity])
        for target_vid in impacted_entities:
            client.insert_impacts(event_id, target_vid)
            impact_count += 1
    print(f"Events upserted: {len(HISTORICAL_EVENTS)}")
    print(f"IMPACTS edges inserted: {impact_count}")


def verify_seeding(client: GraphClient) -> None:
    checks = (
        ("TSMC", 3, {"AAPL", "NVDA", "AMD", "QCOM", "MSFT", "META", "GOOGL"}),
        ("NVDA", 3, {"MSFT", "META", "GOOGL", "AMZN", "TSLA"}),
        ("CRUDE_OIL", 2, {"XOM", "CVX", "TSLA"}),
        ("RARE_EARTH", 2, {"TSLA", "GE", "RTX", "LMT", "NVDA"}),
    )
    print("\nSupply-chain trace verification")
    for target_vid, hops, expected in checks:
        impacted = client.trace_impact(target_vid, hops)
        found = {company["ticker"] for company in impacted}
        missing = sorted(expected - found)
        print(f"trace_impact({target_vid!r}, hops={hops}) -> {len(found)} companies")
        if missing:
            raise RuntimeError(f"{target_vid} trace missing expected tickers: {', '.join(missing)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed QuantVex production graph data.")
    parser.add_argument("--dry-run", action="store_true", help="Print counts without writing to the graph.")
    args = parser.parse_args()

    if args.dry_run:
        print_dry_run()
        return

    with GraphClient() as client:
        create_companies(client)
        create_commodities(client)
        create_depends_on_edges(client)
        create_requires_edges(client)
        create_historical_events(client)
        verify_seeding(client)

    print("\nSEED COMPLETE")


if __name__ == "__main__":
    main()
