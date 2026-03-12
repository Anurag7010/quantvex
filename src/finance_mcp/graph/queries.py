"""
Phase 2 — Parameterised nGQL Query Templates

Every constant in this module is a hard-coded nGQL string that contains
only ``$name`` placeholders — never any runtime values.  Values are
injected by the NebulaGraph protocol layer (via execute_parameter), not
by Python string formatting.

HOW PARAMETERISATION PREVENTS PROMPT INJECTION
-----------------------------------------------
A prompt-injection attack occurs when an LLM is manipulated into placing
adversarial text into a position that is later interpreted as code.  In a
graph query context the attack surface is the query string itself:

    BAD  (injection-vulnerable)
    ────────────────────────────
    ticker = llm_output           # e.g. 'X" DELETE VERTEX "Y'
    query  = f'MATCH (c:Company) WHERE id(c) == "{ticker}" RETURN c'
    session.execute(query)
    # NebulaGraph sees: WHERE id(c) == "X" DELETE VERTEX "Y"
    # → two statements: the MATCH and a silent DELETE

    GOOD (injection-safe, what this module enforces)
    ──────────────────────────────────────────────────
    query  = FETCH_COMPANY          # immutable constant from this module
    params = {"ticker": llm_output} # raw value, not part of the query string
    session.execute_parameter(query, params)
    # Protocol converts {"ticker": "X\" DELETE VERTEX \"Y"}
    # to a typed Value *before* the query reaches the parser.
    # The parser sees a single string literal — the injected nGQL
    # is never parsed as a statement boundary.

The combination of three layers makes injection practically impossible:

    Layer 1 — Immutable templates (this file)
        Values cannot appear in query strings at all.

    Layer 2 — Defense-in-depth marker scan (client._check_params_for_injection)
        String params containing ;  --  /*  */ raise ValueError before
        any network call is made.

    Layer 3 — Protocol-level parameterisation (execute_parameter)
        Even if layers 1 and 2 were somehow bypassed, the graph engine
        receives a typed Value, not a string that could be re-parsed as nGQL.

USAGE
-----
Import the constant you need and pass it to SecureGraphClient._execute():

    from finance_mcp.graph.queries import FETCH_COMPANY

    result = client._execute(FETCH_COMPANY, {"ticker": "AAPL"})

In practice callers use the public wrapper methods on SecureGraphClient
(fetch_company, get_company_dependencies, …) and never touch _execute
directly.  This module is the single source of truth for nGQL so that
query changes are reviewed in one place.
"""

# ============================================================================
# INSERT — write vertices and edges
# ============================================================================

INSERT_COMPANY: str = (
    'INSERT VERTEX Company(ticker, name, sector) '
    'VALUES "{vid}":($ticker, $name, $sector)'
)
"""
Idempotent Company vertex insert.

The VID is embedded as a validated string literal via Python
``.format(vid=...)`` AFTER the caller runs ``_validate_vid()`` on it.
Property values travel as $param via execute_parameter().

Format slot
-----------
{vid}    : str — vertex ID, pre-validated by _validate_vid()

nGQL parameters
---------------
$ticker  : str — stock symbol, e.g. ``"AAPL"``
$name    : str — full company name, e.g. ``"Apple Inc."’’
$sector  : str — GICS sector, e.g. ``"Technology"``

Note: ``IF NOT EXISTS`` was removed so that a duplicate INSERT on an
existing VID simply overwrites the properties (idempotent upsert
semantics).  Use UPSERT VERTEX for conditional updates.
"""

INSERT_COMMODITY: str = (
    'INSERT VERTEX Commodity(name, category) '
    'VALUES "{vid}":($name, $category)'
)
"""
Idempotent Commodity vertex insert.

Format slot
-----------
{vid}     : str — vertex ID, pre-validated by _validate_vid()

nGQL parameters
---------------
$name     : str — human-readable name, e.g. ``"Lithium"``
$category : str — commodity category, e.g. ``"Battery Metals"``
"""

INSERT_EVENT: str = (
    'INSERT VERTEX Event(description, severity) '
    'VALUES "{vid}":($description, $severity)'
)
"""
Insert an Event vertex (non-upsert; use UPSERT_EVENT for overwrite semantics).

Format slot
-----------
{vid}         : str — vertex ID, pre-validated by _validate_vid()

nGQL parameters
---------------
$description  : str — free-text event description
$severity     : int — impact severity 0–10
"""

UPSERT_EVENT: str = (
    'UPSERT VERTEX ON Event "{vid}" '
    'SET Event.description = $description, Event.severity = $severity'
)
"""
Upsert an Event vertex — creates if absent, updates properties if present.

NebulaGraph ``UPSERT VERTEX ON`` semantics:
  - Vertex absent: inserts with the supplied property values; tag fields
    not mentioned in SET receive their default values from the schema.
  - Vertex present: updates only the SET properties; other properties
    are unchanged.

Format slot
-----------
{vid}         : str — vertex ID, pre-validated by _validate_vid()

nGQL parameters
---------------
$description  : str — free-text event description
$severity     : int — impact severity 0–10
"""

# ============================================================================
# INSERT EDGE — write relationships between vertices
# ============================================================================

INSERT_DEPENDS_ON: str = (
    "INSERT EDGE IF NOT EXISTS DEPENDS_ON(weight) "
    "VALUES $src->$dst:($weight)"
)
"""
Create a supply-chain dependency edge between two Company vertices.

Parameters
----------
$src    : str — source Company VID (dependent)
$dst    : str — destination Company VID (supplier)
$weight : float — dependency strength 0.0–1.0

Example: AAPL depends on TSMC → src="AAPL", dst="TSM"
"""

INSERT_REQUIRES: str = (
    "INSERT EDGE IF NOT EXISTS REQUIRES(volume) "
    "VALUES $src->$dst:($volume)"
)
"""
Record that a Company requires a Commodity.

Parameters
----------
$src    : str — Company VID
$dst    : str — Commodity VID
$volume : int — annual demand volume (arbitrary units, domain-specific)
"""

INSERT_IMPACTS: str = (
    "INSERT EDGE IF NOT EXISTS IMPACTS(impact_time) "
    "VALUES $src->$dst:(datetime($impact_time))"
)
"""
Record that an Event impacts a Company.

Parameters
----------
$src         : str — Event VID
$dst         : str — Company VID
$impact_time : str — ISO-8601 datetime string, e.g. ``"2026-03-09T00:00:00"``
"""

# ============================================================================
# FETCH / LOOKUP — read single vertices
# ============================================================================

FETCH_COMPANY: str = (
    "MATCH (v:Company) WHERE id(v) == $ticker "
    "RETURN properties(v) AS props"
)
"""
Retrieve all properties of a Company vertex.

Parameters
----------
$ticker : str — vertex ID / stock ticker, e.g. ``"AAPL"``

Result columns
--------------
props : map — ``{ticker, name, sector}``
"""

FETCH_COMMODITY: str = (
    "MATCH (v:Commodity) WHERE id(v) == $commodity_id "
    "RETURN properties(v) AS props"
)
"""
Retrieve all properties of a Commodity vertex.

Parameters
----------
$commodity_id : str — vertex ID, e.g. ``"CRUDE_OIL"``

Result columns
--------------
props : map — ``{name, category}``
"""

FETCH_EVENT: str = (
    "MATCH (v:Event) WHERE id(v) == $event_id "
    "RETURN properties(v) AS props"
)
"""
Retrieve all properties of an Event vertex.

Parameters
----------
$event_id : str — vertex ID, e.g. ``"EVT_2026_001"``

Result columns
--------------
props : map — ``{description, severity}``
"""

# ============================================================================
# TRAVERSAL — multi-hop graph queries
# ============================================================================

TRACE_SUPPLY_CHAIN: str = (
    "MATCH (s:Company)-[e:DEPENDS_ON*1..{depth}]->(d:Company) "
    "WHERE id(s) == $ticker "
    "RETURN id(s) AS supplier, id(d) AS dependent, e.weight AS weight "
    "ORDER BY weight DESC"
)
"""
Walk the DEPENDS_ON graph outward from a Company up to ``depth`` hops.

Returns every supplier / dependent pair found along that walk, ordered by
descending edge weight so the strongest dependencies surface first.

Parameters
----------
{depth}  : int  — Python format slot (NOT a nGQL param).  Injected by
                  SecureGraphClient.get_company_dependencies() AFTER
                  validating that depth is an integer in [1, 5].  It controls
                  graph structure (hop count) not data, so embedding a
                  validated int literal is safe.
$ticker  : str  — starting Company VID (nGQL parameter)

Result columns
--------------
supplier  : str   — source company VID at each hop
dependent : str   — destination company VID at each hop
weight    : float — DEPENDS_ON edge weight

Note: NebulaGraph 3.x does not support parameters in the step-count
position of GO or in multi-hop MATCH patterns, so depth must be an
embedded literal.  The caller enforces bounds [1, 5] before this
template is formatted.
"""

GET_COMPANY_COMMODITIES: str = (
    "MATCH (s:Company)-[e:REQUIRES]->(d:Commodity) WHERE id(s) == $ticker "
    "RETURN id(d) AS commodity, e.volume AS volume "
    "ORDER BY volume DESC"
)
"""
List all Commodity vertices required by a Company, by descending volume.

Parameters
----------
$ticker : str — Company VID

Result columns
--------------
commodity : str — Commodity VID
volume    : int — demand volume
"""

GET_EVENTS_FOR_COMPANY: str = (
    "MATCH (s:Event)-[e:IMPACTS]->(d:Company) WHERE id(d) == $ticker "
    "RETURN id(s) AS event_id, e.impact_time AS impact_time "
    "ORDER BY impact_time DESC"
)
"""
Find all Event vertices that impact a Company.

Parameters
----------
$ticker : str — Company VID

Result columns
--------------
event_id    : str      — Event VID
impact_time : datetime — time the impact was recorded
"""

LOOKUP_COMPANIES_BY_SECTOR: str = (
    "MATCH (v:Company) WHERE v.Company.sector == $sector "
    "RETURN id(v) AS ticker, v.Company.name AS name"
)
"""
Find all Company vertices in a given sector.

Requires: tag index ``idx_company_sector`` on ``Company(sector(64))``.

Parameters
----------
$sector : str — GICS sector string, e.g. ``"Technology"``

Result columns
--------------
ticker : str — Company VID / ticker symbol
name   : str — company name
"""

LOOKUP_EVENTS_ABOVE_SEVERITY: str = (
    "MATCH (v:Event) WHERE v.Event.severity >= $min_severity "
    "RETURN id(v) AS event_id, v.Event.description AS description, "
    "v.Event.severity AS severity "
    "ORDER BY severity DESC"
)
"""
Find all Event vertices at or above a severity threshold.

Parameters
----------
$min_severity : int — lower-bound severity (inclusive), 0–10

Result columns
--------------
event_id    : str — Event VID
description : str — event description
severity    : int — severity score
"""

# ============================================================================
# IMPACT REASONING — downstream propagation of supply shocks
# ============================================================================

TRACE_IMPACT: str = (
    "MATCH (impacted:Company)-[:DEPENDS_ON*1..{max_hops}]->(target:Company) "
    "WHERE id(target) == $ticker "
    "RETURN DISTINCT id(impacted) AS impacted_ticker, "
    "impacted.Company.name AS name, impacted.Company.sector AS sector"
)

FIND_COMPANIES_REQUIRING_COMMODITY: str = (
    "MATCH (c:Company)-[:REQUIRES]->(com:Commodity) "
    "WHERE id(com) == $commodity_id "
    "RETURN id(c) AS ticker, c.Company.name AS name, c.Company.sector AS sector"
)
"""
Find all Company vertices that directly require a given commodity.

Used to propagate a commodity-level supply shock (e.g. crude oil shortage
from geopolitical conflict) to the companies that depend on that commodity,
before tracing their downstream DEPENDS_ON cascade.

nGQL parameter
--------------
$commodity_id : str — Commodity VID, e.g. ``"CRUDE_OIL"`` or ``"SEMICONDUCTOR"``

Result columns
--------------
ticker  : str — Company VID
name    : str — company full name
sector  : str — GICS sector
"""
"""
Find all Company vertices that transitively depend on a target company.

Traverses DEPENDS_ON edges **in reverse**:
  ``(impacted) -[:DEPENDS_ON*1..N]-> (target)``

This models downstream propagation of a supply shock: every company X
that has a DEPENDS_ON path leading to the target will appear in the
result, regardless of hop distance up to ``max_hops``.

Example: ``trace_impact("TSMC", max_hops=3)``
  Returns all companies (Apple, Nvidia, …) that directly or transitively
  depend on TSMC in the supply graph.

Format slot (Python str.format — not a nGQL param)
-----------
{max_hops} : int — maximum traversal depth, validated to [1, 5] by
                   SecureGraphClient.trace_impact() before this template
                   is formatted.  A validated integer cannot inject nGQL.

nGQL parameter
--------------
$ticker    : str — target company VID, e.g. ``"TSMC"``

Result columns
--------------
impacted_ticker : str — VID of each impacted company
name            : str — company name
sector          : str — GICS sector
"""
