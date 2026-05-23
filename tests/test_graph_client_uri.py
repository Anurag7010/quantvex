"""Unit tests for GraphClient URI override via NEO4J_URI env var."""
import os
from unittest.mock import patch
import pytest


def test_graph_client_uses_bolt_by_default():
    from finance_mcp.graph.client import GraphClient
    env = {k: v for k, v in os.environ.items() if k != "NEO4J_URI"}
    with patch.dict(os.environ, env, clear=True):
        client = GraphClient(host="localhost", port=7687)
        assert client._uri == "bolt://localhost:7687"


def test_graph_client_uses_neo4j_uri_when_set():
    from finance_mcp.graph.client import GraphClient
    aura_uri = "neo4j+s://abc123.databases.neo4j.io"
    with patch.dict(os.environ, {"NEO4J_URI": aura_uri}):
        client = GraphClient(host="localhost", port=7687)
        assert client._uri == aura_uri


def test_graph_client_ignores_host_port_when_uri_set():
    from finance_mcp.graph.client import GraphClient
    aura_uri = "neo4j+s://abc123.databases.neo4j.io"
    with patch.dict(os.environ, {"NEO4J_URI": aura_uri}):
        client = GraphClient(host="should-be-ignored", port=9999)
        assert "should-be-ignored" not in client._uri
        assert client._uri == aura_uri
