"""
Seed AuraDB via HTTP REST API (port 443) — bypasses Bolt/driver issues.

Usage:
    python scripts/seed_via_http.py \
        --uri neo4j+s://41f9e152.databases.neo4j.io \
        --password IU-KwWM9jH2sHluMoDVOq3fVSP6uIYjh0ZRKjDNPaZU
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import urllib.request, urllib.error, base64

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from scripts.seed_production_data import (
    COMPANIES, COMMODITIES, DEPENDS_ON_EDGES, REQUIRES_EDGES, HISTORICAL_EVENTS, SEVERITY_SCORE
)


def run_query(base_url: str, auth_header: str, query: str, params: dict = {}) -> dict:
    payload = json.dumps({"statements": [{"statement": query, "parameters": params}]}).encode()
    req = urllib.request.Request(
        f"{base_url}/db/neo4j/tx/commit",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": auth_header},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read())
    errors = result.get("errors", [])
    if errors:
        raise RuntimeError(errors[0].get("message", str(errors)))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True, help="e.g. neo4j+s://41f9e152.databases.neo4j.io")
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    host = args.uri.replace("neo4j+s://", "").replace("neo4j+ssc://", "").replace("bolt+s://", "").rstrip("/")
    base_url = f"https://{host}"
    token = base64.b64encode(f"{args.user}:{args.password}".encode()).decode()
    auth_header = f"Basic {token}"

    print(f"Connecting to {base_url} ...")
    run_query(base_url, auth_header, "RETURN 1")
    print("Connection OK")

    print("Seeding companies...")
    for ticker, name, sector in COMPANIES:
        run_query(base_url, auth_header,
            "MERGE (c:Company {ticker: $ticker}) SET c.name=$name, c.sector=$sector",
            {"ticker": ticker, "name": name, "sector": sector})
    print(f"  {len(COMPANIES)} companies done")

    print("Seeding commodities...")
    for cid, name, category in COMMODITIES:
        run_query(base_url, auth_header,
            "MERGE (c:Commodity {id: $id}) SET c.name=$name, c.category=$category",
            {"id": cid, "name": name, "category": category})
    print(f"  {len(COMMODITIES)} commodities done")

    print("Seeding DEPENDS_ON edges...")
    for src, dst, weight in DEPENDS_ON_EDGES:
        run_query(base_url, auth_header,
            "MATCH (a:Company {ticker:$src}), (b:Company {ticker:$dst}) "
            "MERGE (a)-[r:DEPENDS_ON]->(b) SET r.weight=$weight",
            {"src": src, "dst": dst, "weight": weight})
    print(f"  {len(DEPENDS_ON_EDGES)} edges done")

    print("Seeding REQUIRES edges...")
    for src, dst, volume in REQUIRES_EDGES:
        run_query(base_url, auth_header,
            "MATCH (a:Company {ticker:$src}), (b:Commodity {id:$dst}) "
            "MERGE (a)-[r:REQUIRES]->(b) SET r.volume=$volume",
            {"src": src, "dst": dst, "volume": volume})
    print(f"  {len(REQUIRES_EDGES)} edges done")

    print("Seeding events...")
    for event_id, description, severity, impacted in HISTORICAL_EVENTS:
        score = SEVERITY_SCORE[severity]
        run_query(base_url, auth_header,
            "MERGE (e:Event {id:$id}) SET e.description=$desc, e.severity=$sev",
            {"id": event_id, "desc": description, "sev": score})
        for target in impacted:
            run_query(base_url, auth_header,
                "MATCH (e:Event {id:$eid}) "
                "OPTIONAL MATCH (c:Company {ticker:$tid}) "
                "OPTIONAL MATCH (com:Commodity {id:$tid}) "
                "WITH e, coalesce(c, com) AS target WHERE target IS NOT NULL "
                "MERGE (e)-[:IMPACTS]->(target)",
                {"eid": event_id, "tid": target})
    print(f"  {len(HISTORICAL_EVENTS)} events done")

    print("\nSeeding complete!")


if __name__ == "__main__":
    main()
