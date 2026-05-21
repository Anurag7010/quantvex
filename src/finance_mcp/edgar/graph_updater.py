"""
finance_mcp.edgar.graph_updater
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Writes EDGAR-derived supplier / customer relationships into Memgraph.

Public API
----------
async def update_graph_from_filing(
    ticker: str,
    relationships: List[SupplierRelationship],
    filing_date: str = "",
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> UpdateResult
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

from finance_mcp.edgar.supplier_extractor import SupplierRelationship
from finance_mcp.graph.client import GraphClient, DEFAULT_HOST, DEFAULT_PORT

logger = logging.getLogger(__name__)


@dataclass
class UpdateResult:
    ticker: str
    new_edges_added: int = 0
    updated_edges: int = 0
    companies_discovered: int = 0
    filing_date: str = ""
    errors: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "new_edges_added": self.new_edges_added,
            "updated_edges": self.updated_edges,
            "companies_discovered": self.companies_discovered,
            "filing_date": self.filing_date,
            "errors": self.errors,
        }


async def update_graph_from_filing(
    ticker: str,
    relationships: List[SupplierRelationship],
    filing_date: str = "",
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> UpdateResult:
    """
    Write EDGAR-derived relationships to Memgraph as DEPENDS_ON edges.

    Edge semantics
    --------------
    supplier  → (ticker)-[:DEPENDS_ON]->(entity_ticker)
                  "ticker depends on this supplier"
    customer  → (entity_ticker)-[:DEPENDS_ON]->(ticker)
                  "this customer depends on ticker"

    Both edges are tagged with source='EDGAR' and updated_at timestamp.
    Existing edges are updated (weight + updated_at). New edges are counted
    separately from updated ones.
    """
    result = UpdateResult(ticker=ticker, filing_date=filing_date)
    if not relationships:
        return result

    updated_at = datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()

    with GraphClient(host=host, port=port) as client:
        for rel in relationships:
            try:
                # ----------------------------------------------------------
                # Ensure the related Company vertex exists
                # ----------------------------------------------------------
                client._run(
                    "MERGE (c:Company {ticker: $ticker}) "
                    "ON CREATE SET c.name = $name, c.sector = 'Unknown' "
                    "ON MATCH SET c.name = CASE WHEN c.name IS NULL OR c.name = '' "
                    "THEN $name ELSE c.name END",
                    ticker=rel.supplier_ticker,
                    name=rel.supplier_name,
                )
                result.companies_discovered += 1

                # ----------------------------------------------------------
                # Determine edge direction based on relationship type
                # ----------------------------------------------------------
                if rel.relationship_type == "supplier":
                    src, dst = ticker, rel.supplier_ticker
                else:
                    # customer: the related company depends on the filing company
                    src, dst = rel.supplier_ticker, ticker

                # ----------------------------------------------------------
                # Check whether the edge already exists
                # ----------------------------------------------------------
                existing = client._run(
                    "MATCH (a:Company {ticker: $src})-[r:DEPENDS_ON]->(b:Company {ticker: $dst}) "
                    "RETURN r.source AS source",
                    src=src, dst=dst,
                )
                is_new = len(existing) == 0

                # ----------------------------------------------------------
                # MERGE edge with EDGAR metadata
                # ----------------------------------------------------------
                client._run(
                    "MATCH (a:Company {ticker: $src}), (b:Company {ticker: $dst}) "
                    "MERGE (a)-[r:DEPENDS_ON]->(b) "
                    "SET r.weight = $weight, r.source = 'EDGAR', r.updated_at = $updated_at",
                    src=src,
                    dst=dst,
                    weight=rel.dependency_strength,
                    updated_at=updated_at,
                )

                if is_new:
                    result.new_edges_added += 1
                else:
                    result.updated_edges += 1

            except Exception as exc:
                msg = f"{rel.supplier_ticker}: {exc}"
                logger.warning("graph_updater_edge_error %s", msg)
                result.errors.append(msg)

    logger.info(
        "graph_updater: ticker=%s new=%d updated=%d discovered=%d errors=%d",
        ticker,
        result.new_edges_added,
        result.updated_edges,
        result.companies_discovered,
        len(result.errors),
    )
    return result
