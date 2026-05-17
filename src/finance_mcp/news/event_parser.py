"""
Phase 3 — Event Parser

Converts a ``NewsArticle`` into a ``ParsedEvent`` by scanning the
headline and description for:
  1. Disruption keywords → severity score and event type
  2. Company tickers     → impacted Company entities
  3. Commodity names     → impacted Commodity entities

Design principles
-----------------
* No external dependencies — pure Python string matching.
* Case-insensitive matching throughout.
* Multiple keywords in a single article accumulate to a max severity cap
  rather than inflating unboundedly.
* The entity lists returned are Commodity/Company VID strings that the
  event ingestor can insert directly as graph vertices.
* A later phase may replace keyword rules with an LLM extraction call;
  the ParsedEvent contract is stable either way.

"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ParsedEvent — the output contract
# ---------------------------------------------------------------------------

@dataclass
class ImpactedEntity:
    """
    A graph entity (Company or Commodity) that this event affects.

    Attributes
    ----------
    entity_id   : str — vertex ID usable directly in NebulaGraph, e.g. "TSMC"
    entity_type : str — "company" | "commodity"
    name        : str — human-readable label
    """
    entity_id: str
    entity_type: str   # "company" | "commodity"
    name: str

    def as_dict(self) -> dict:
        return {"entity_id": self.entity_id, "entity_type": self.entity_type, "name": self.name}


@dataclass
class ParsedEvent:
    """
    Structured graph event derived from a news article.

    Attributes
    ----------
    event_id          : str              — stable deterministic VID for the graph
    description       : str              — concise event description (≤200 chars)
    severity          : int              — 0–10; higher = more disruptive
    event_type        : str              — primary disruption category
    impacted_entities : List[ImpactedEntity] — companies and commodities affected
    published_at      : datetime         — article publication timestamp (UTC)
    source_url        : str              — original article URL (for lineage)
    """
    event_id: str
    description: str
    severity: int
    event_type: str
    impacted_entities: List[ImpactedEntity] = field(default_factory=list)
    published_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    source_url: str = ""

    def as_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "description": self.description,
            "severity": self.severity,
            "event_type": self.event_type,
            "impacted_entities": [e.as_dict() for e in self.impacted_entities],
            "published_at": self.published_at.isoformat(),
            "source_url": self.source_url,
        }


# ---------------------------------------------------------------------------
# Disruption keyword rules
# ---------------------------------------------------------------------------
# Each entry: (regex_pattern, severity, event_type_label)
# Patterns are matched against the lowercased concatenation of title + description.
# First match sets the base severity; subsequent matches raise it up to the cap.

_DISRUPTION_RULES: List[Tuple[str, int, str]] = [
    # Natural disasters
    (r"\bearthquake\b",          8,  "natural_disaster"),
    (r"\btsunami\b",             9,  "natural_disaster"),
    (r"\bflood(?:ing)?\b",       7,  "natural_disaster"),
    (r"\btyphoon\b",             8,  "natural_disaster"),
    (r"\bhurricane\b",           8,  "natural_disaster"),
    (r"\bwildfires?\b",          6,  "natural_disaster"),

    # Geopolitical / conflict
    (r"\bwar\b",                 9,  "geopolitical"),
    (r"\bsanction(?:s|ed)?\b",   8,  "geopolitical"),
    (r"\bembargo\b",             8,  "geopolitical"),
    (r"\bblockade\b",            7,  "geopolitical"),
    (r"\bconflict\b",            7,  "geopolitical"),
    (r"\binvasion\b",            9,  "geopolitical"),
    (r"\bexports?\s+ban\b",       8,  "geopolitical"),
    (r"\btrade\s+war\b",         7,  "geopolitical"),

    # Industrial / operational
    (r"\bfactory\s+(?:fire|explosion|outage|shutdown|closure)\b", 8, "industrial"),
    (r"\bexplosion\b",           8,  "industrial"),
    (r"\bfire\b",                6,  "industrial"),
    (r"\boutage\b",              6,  "industrial"),
    (r"\bshutdown\b",            6,  "industrial"),
    (r"\bclosure\b",             5,  "industrial"),
    (r"\bplant\s+closure\b",     7,  "industrial"),
    (r"\bproduction\s+halt\b",   8,  "industrial"),
    (r"\bhalt(?:ed|s)?\b",       6,  "industrial"),
    (r"\bdisrupt(?:ion|ed|s)?\b",5,  "industrial"),

    # Labour
    (r"\bstrike\b",              7,  "labour"),
    (r"\blockout\b",             7,  "labour"),
    (r"\blabou?r\s+(?:dispute|action|unrest)\b", 6, "labour"),
    (r"\bworker\s+protest\b",    5,  "labour"),

    # Supply chain
    (r"\bshortage\b",            6,  "supply_chain"),
    (r"\bsupply\s+crunch\b",     7,  "supply_chain"),
    (r"\bbottleneck\b",          5,  "supply_chain"),
    (r"\bdelay\b",               4,  "supply_chain"),
    (r"\bbacklog\b",             4,  "supply_chain"),
    (r"\bsupply\s+chain\s+(?:crisis|disruption|shock)\b", 7, "supply_chain"),
    (r"\bcapacity\s+constraint\b",5, "supply_chain"),

    # Financial distress
    (r"\bbankruptcy\b",          8,  "financial"),
    (r"\binsolvency\b",          8,  "financial"),
    (r"\bdefault\b",             7,  "financial"),
    (r"\bcredit\s+downgrade\b",  6,  "financial"),
    (r"\bliquidity\s+crisis\b",  7,  "financial"),

    # Trade & regulatory — common in tech/semiconductor news
    (r"\btariff(?:s)?\b",                               5,  "geopolitical"),
    (r"\bexport\s+(?:control|restriction|ban)\b",       7,  "geopolitical"),
    (r"\bimport\s+(?:ban|restriction)\b",               7,  "geopolitical"),
    (r"\bentity\s+list\b",                              7,  "geopolitical"),
    (r"\bblacklist(?:ed)?\b",                           6,  "geopolitical"),
    (r"\bchip\s+ban\b",                                 8,  "geopolitical"),
    (r"\btech(?:nology)?\s+ban\b",                      7,  "geopolitical"),
    (r"\bde-?coupling\b",                               5,  "geopolitical"),

    # Earnings / financial signals
    (r"\bearnings\s+miss\b",                            5,  "financial"),
    (r"\bguidance\s+(?:cut|reduced|lowered|slashed)\b", 5,  "financial"),
    (r"\blower(?:ed)?\s+(?:guidance|outlook|forecast)\b", 4, "financial"),
    (r"\bprofit\s+warning\b",                           6,  "financial"),
    (r"\bdowngrade\b",                                  4,  "financial"),
    (r"\bwrite-?down\b",                                5,  "financial"),
    (r"\bimpairment\b",                                 4,  "financial"),

    # Supply chain — softer signals
    (r"\bproduction\s+(?:cut|cuts|reduced|slowdown|pause)\b", 5, "supply_chain"),
    (r"\boutput\s+(?:cut|reduced|slashed|decline)\b",   5,  "supply_chain"),
    (r"\bcapacity\s+(?:crunch|shortage|tight|constrained)\b", 5, "supply_chain"),
    (r"\binventory\s+(?:low|tight|depleted|shortage|glut)\b", 4, "supply_chain"),
    (r"\bsupply\s+tight\b",                             4,  "supply_chain"),
    (r"\bsupplier\s+(?:issue|problem|warning|risk|shortage)\b", 4, "supply_chain"),
    (r"\bheadwind(?:s)?\b",                             3,  "supply_chain"),
    (r"\bpressure(?:d)?\b",                             2,  "supply_chain"),
    (r"\bslowdown\b",                                   3,  "supply_chain"),
    (r"\bconcern(?:s)?\b",                              2,  "supply_chain"),
    (r"\bsupply\s+squeeze\b",                           5,  "supply_chain"),
    (r"\bdemand\s+(?:drop|decline|slump|shock)\b",      4,  "supply_chain"),
    (r"\bover(?:supply|capacity)\b",                    3,  "supply_chain"),

    # Operational — softer
    (r"\bplant\s+(?:issue|problem|idle|reduced|pause)\b", 4, "industrial"),
    (r"\bfacility\s+(?:closure|shutdown|issue|damaged)\b", 6, "industrial"),
    (r"\bmaintenance\s+(?:halt|shutdown|outage)\b",     4,  "industrial"),
    (r"\baffect(?:ed|s|ing)?\b",                        2,  "supply_chain"),
    (r"\bexpos(?:ed|ure|ing)\b",                        2,  "supply_chain"),
    (r"\brisk(?:s|ing)?\b",                             1,  "supply_chain"),
    (r"\bvulnerab(?:le|ility)\b",                       3,  "supply_chain"),
]

# Pre-compile regex patterns for performance
_COMPILED_RULES: List[Tuple[re.Pattern, int, str]] = [
    (re.compile(pat, re.IGNORECASE), sev, etype)
    for pat, sev, etype in _DISRUPTION_RULES
]

# Maximum severity regardless of how many keywords match
_SEVERITY_CAP: int = 10

# Minimum severity for an event to be considered meaningful
_SEVERITY_MIN: int = 1


# ---------------------------------------------------------------------------
# Entity recognition tables
# ---------------------------------------------------------------------------
# Company: maps keyword pattern → (entity_id, human name)
# entity_id is the NebulaGraph VID used in insert_company / DEPENDS_ON edges.

_COMPANY_PATTERNS: List[Tuple[str, str, str]] = [
    # (regex, entity_id, display_name)
    (r"\bTSMC\b|taiwan\s+semiconductor",        "TSMC",   "Taiwan Semiconductor Mfg."),
    (r"\bApple\b",                               "AAPL",   "Apple Inc."),
    (r"\bNVIDIA\b|\bNVDA\b",                     "NVDA",   "NVIDIA Corp."),
    (r"\bAMD\b|advanced\s+micro\s+devices",      "AMD",    "Advanced Micro Devices"),
    (r"\bQualcomm\b|\bQCOM\b",                   "QCOM",   "Qualcomm Inc."),
    (r"\bIntel\b|\bINTC\b",                      "INTC",   "Intel Corp."),
    (r"\bSamsung\b",                             "SMSNG",  "Samsung Electronics"),
    (r"\bSK\s+Hynix\b",                          "SKHYNX", "SK Hynix"),
    (r"\bMicron\b|\bMU\b",                       "MU",     "Micron Technology"),
    (r"\bASML\b",                                "ASML",   "ASML Holding"),
    (r"\bBoeing\b|\bBA\b",                       "BA",     "Boeing Co."),
    (r"\bAirbus\b",                              "AIR",    "Airbus SE"),
    (r"\bTesla\b|\bTSLA\b",                      "TSLA",   "Tesla Inc."),
    (r"\bFord\b|\bF\b",                          "F",      "Ford Motor"),
    (r"\bGM\b|general\s+motors",                 "GM",     "General Motors"),
    (r"\bVolkswagen\b|\bVW\b",                   "VW",     "Volkswagen AG"),
    (r"\bRio\s+Tinto\b",                         "RIO",    "Rio Tinto"),
    (r"\bBHP\b",                                 "BHP",    "BHP Group"),
    (r"\bGlencore\b",                            "GLEN",   "Glencore"),
    (r"\bAlbemarle\b|\bALB\b",                   "ALB",    "Albemarle Corp."),
    (r"\bExxon\b|\bXOM\b",                       "XOM",    "ExxonMobil"),
    (r"\bShell\b|\bSHEL\b",                      "SHEL",   "Shell plc"),
    (r"\bBP\b",                                  "BP",     "BP plc"),
    (r"\bChevron\b|\bCVX\b",                     "CVX",    "Chevron Corp."),
    (r"\bUMC\b|united\s+microelectronics",       "UMC",    "United Microelectronics"),
    (r"\bGlobalFoundries\b",                     "GFS",    "GlobalFoundries"),
    (r"\bMicrosoft\b|\bMSFT\b",                 "MSFT",   "Microsoft Corp."),
    (r"\bAmazon\b|\bAMZN\b",                    "AMZN",   "Amazon.com Inc."),
    (r"\bMeta\b|\bFacebook\b|\bMETA\b",         "META",   "Meta Platforms"),
    (r"\bGoogle\b|\bAlphabet\b|\bGOOGL?\b",     "GOOGL",  "Alphabet Inc."),
    (r"\bNetflix\b|\bNFLX\b",                   "NFLX",   "Netflix Inc."),
    (r"\bBroadcom\b|\bAVGO\b",                  "AVGO",   "Broadcom Inc."),
    (r"\bTexas\s+Instruments\b|\bTXN\b",        "TXN",    "Texas Instruments"),
    (r"\bApplied\s+Materials\b|\bAMAT\b",       "AMAT",   "Applied Materials"),
    (r"\bLam\s+Research\b|\bLRCX\b",            "LRCX",   "Lam Research"),
    (r"\bKLA(?:\s+Corp\.?)?\b|\bKLAC\b",        "KLAC",   "KLA Corp."),
    (r"\bON\s+Semiconductor\b|\bONSemi\b|\bON\b", "ON",   "ON Semiconductor"),
    (r"\bNXP\s+Semiconductors\b|\bNXPI\b",      "NXPI",   "NXP Semiconductors"),
    (r"\bSTMicroelectronics\b|\bSTM\b",          "STM",    "STMicroelectronics"),
    (r"\bInfineon\b",                            "IFX",    "Infineon Technologies"),
    (r"\bMarvell\b|\bMRVL\b",                   "MRVL",   "Marvell Technology"),
    (r"\bMediaTek\b",                            "MDTK",   "MediaTek Inc."),
    (r"\bHuawei\b",                              "HUAWEI", "Huawei Technologies"),
    (r"\bSMIC\b|semiconductor\s+manufacturing\s+international", "SMIC", "SMIC"),
]

# Commodity: maps keyword pattern → (entity_id, display_name)
_COMMODITY_PATTERNS: List[Tuple[str, str, str]] = [
    (r"\bsemiconductor(?:s)?\b|\bchip(?:s)?\b|\bwafer(?:s)?\b",
                                              "SEMICONDUCTOR", "Semiconductor"),
    (r"\blithium\b",                          "LITHIUM",        "Lithium"),
    (r"\bcobalt\b",                           "COBALT",         "Cobalt"),
    (r"\bnickel\b",                           "NICKEL",         "Nickel"),
    (r"\bcopper\b",                           "COPPER",         "Copper"),
    (r"\bpalladium\b",                        "PALLADIUM",      "Palladium"),
    (r"\bplatinum\b",                         "PLATINUM",       "Platinum"),
    (r"\brare\s+earth(?:s)?\b",               "RARE_EARTH",     "Rare Earth Elements"),
    (r"\bgallium\b",                          "GALLIUM",        "Gallium"),
    (r"\bgermanium\b",                        "GERMANIUM",      "Germanium"),
    (r"\bneon\b",                             "NEON_GAS",       "Neon Gas"),
    (r"\bcr(?:ude)?\s+oil\b|\bpetroleum\b",  "CRUDE_OIL",      "Crude Oil"),
    (r"\bnatural\s+gas\b",                    "NATURAL_GAS",    "Natural Gas"),
    (r"\bsteel\b",                            "STEEL",          "Steel"),
    (r"\balumini?um\b",                       "ALUMINUM",       "Aluminum"),
    (r"\bthermal\s+coal\b|\bcoking\s+coal\b|\bcoal\b",
                                              "COAL",           "Coal"),
]

# Pre-compile entity patterns
_COMPILED_COMPANIES: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(pat, re.IGNORECASE), eid, name)
    for pat, eid, name in _COMPANY_PATTERNS
]
_COMPILED_COMMODITIES: List[Tuple[re.Pattern, str, str]] = [
    (re.compile(pat, re.IGNORECASE), eid, name)
    for pat, eid, name in _COMMODITY_PATTERNS
]


# ---------------------------------------------------------------------------
# EventParser
# ---------------------------------------------------------------------------

class EventParser:
    """
    Converts a ``NewsArticle`` into a ``ParsedEvent`` using keyword rules.

    Usage
    -----
        from finance_mcp.news.event_parser import EventParser
        from finance_mcp.news.news_client import NewsClient

        client = NewsClient()
        parser = EventParser()

        articles = await client.fetch_semiconductor_news(limit=10)
        events = [parser.parse_news_article(a) for a in articles]
        # Filter to articles that actually contain a disruption signal
        significant = [e for e in events if e is not None]
    """

    def parse_news_article(self, article) -> Optional[ParsedEvent]:
        """
        Parse a single ``NewsArticle`` into a ``ParsedEvent``.

        Returns ``None`` when the article contains no recognisable
        disruption signal (severity stays at 0 after scanning all rules).

        Parameters
        ----------
        article : NewsArticle
            Article as returned by ``NewsClient.fetch_market_news()``.

        Returns
        -------
        ParsedEvent | None
        """
        # ------------------------------------------------------------------
        # Build searchable text (title weighted by repeating it)
        # ------------------------------------------------------------------
        title = (article.title or "").strip()
        description = (article.description or "").strip()
        # Repeat the title so headline keywords carry more weight
        search_text = f"{title} {title} {description}".lower()

        # ------------------------------------------------------------------
        # Disruption scoring
        # ------------------------------------------------------------------
        severity: int = 0
        event_type: str = "disruption"
        matched_labels: List[str] = []

        for pattern, rule_severity, rule_type in _COMPILED_RULES:
            if pattern.search(search_text):
                if severity == 0:
                    event_type = rule_type  # first match sets the primary type
                severity = min(severity + rule_severity, _SEVERITY_CAP)
                matched_labels.append(rule_type)

        if severity < _SEVERITY_MIN:
            logger.debug("event_parser: no disruption signal in %r", title[:60])
            return None

        # ------------------------------------------------------------------
        # Entity extraction
        # ------------------------------------------------------------------
        seen_ids: set = set()
        entities: List[ImpactedEntity] = []

        for pattern, entity_id, name in _COMPILED_COMPANIES:
            if entity_id not in seen_ids and pattern.search(search_text):
                entities.append(
                    ImpactedEntity(entity_id=entity_id, entity_type="company", name=name)
                )
                seen_ids.add(entity_id)

        for pattern, entity_id, name in _COMPILED_COMMODITIES:
            if entity_id not in seen_ids and pattern.search(search_text):
                entities.append(
                    ImpactedEntity(entity_id=entity_id, entity_type="commodity", name=name)
                )
                seen_ids.add(entity_id)

        # ------------------------------------------------------------------
        # Build description — title + first 150 chars of description body
        # ------------------------------------------------------------------
        if description and description != title:
            combined = f"{title}. {description[:150]}"
        else:
            combined = title
        description_text = combined[:200] if combined else description[:200]

        # ------------------------------------------------------------------
        # Generate a stable, deterministic event_id from the URL + title
        # so duplicate runs produce identical VIDs (idempotent upserts).
        # ------------------------------------------------------------------
        hash_input = f"{article.url}|{title}".encode("utf-8")
        short_hash = hashlib.sha1(hash_input).hexdigest()[:12]
        event_id = f"EVT_{short_hash}"

        event = ParsedEvent(
            event_id=event_id,
            description=description_text,
            severity=min(severity, _SEVERITY_CAP),
            event_type=event_type,
            impacted_entities=entities,
            published_at=article.published_at,
            source_url=article.url,
        )

        logger.info(
            "event_parser: parsed event_id=%r severity=%d type=%s entities=%d title=%r",
            event_id,
            event.severity,
            event_type,
            len(entities),
            title[:60],
        )
        return event

    def parse_articles(self, articles) -> List[ParsedEvent]:
        """
        Parse a list of articles, filtering out non-disruptive ones.

        Parameters
        ----------
        articles : List[NewsArticle]

        Returns
        -------
        List[ParsedEvent]  — only articles that produced a disruption signal.
        """
        events = []
        for article in articles:
            event = self.parse_news_article(article)
            if event is not None:
                events.append(event)
        logger.info(
            "event_parser: %d/%d articles produced events",
            len(events), len(articles),
        )
        return events
