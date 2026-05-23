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
