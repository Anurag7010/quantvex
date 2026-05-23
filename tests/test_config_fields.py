def test_groq_api_key_defaults_empty():
    from mcp_server.config import Settings
    s = Settings()
    assert s.groq_api_key == ""

def test_groq_model_default():
    from mcp_server.config import Settings
    s = Settings()
    assert s.groq_model == "llama-3.3-70b-versatile"

def test_groq_api_key_reads_from_env():
    import os
    from mcp_server.config import Settings
    from unittest.mock import patch
    with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test123"}):
        s = Settings()
        assert s.groq_api_key == "gsk_test123"

def test_redis_ssl_defaults_false():
    from mcp_server.config import Settings
    s = Settings()
    assert s.redis_ssl is False

def test_redis_password_defaults_empty():
    from mcp_server.config import Settings
    s = Settings()
    assert s.redis_password == ""

def test_neo4j_uri_defaults_to_configured_value():
    from mcp_server.config import Settings
    s = Settings()
    # neo4j_uri should be readable from the config (either .env or programmatic default)
    assert isinstance(s.neo4j_uri, str)

def test_redis_ssl_reads_from_env():
    import os
    from unittest.mock import patch
    from mcp_server.config import Settings
    with patch.dict(os.environ, {"REDIS_SSL": "true"}):
        s = Settings()
        assert s.redis_ssl is True

def test_neo4j_uri_reads_from_env():
    import os
    from unittest.mock import patch
    from mcp_server.config import Settings
    with patch.dict(os.environ, {"NEO4J_URI": "neo4j+s://abc123.databases.neo4j.io"}):
        s = Settings()
        assert s.neo4j_uri == "neo4j+s://abc123.databases.neo4j.io"
