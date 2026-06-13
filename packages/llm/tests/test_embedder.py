import pytest
from devmanager_llm.embedder import (  # noqa: F401  (Embedder re-imported below)
    AzureOpenAIEmbedder,
    Embedder,
    OllamaEmbedder,
    OpenAIEmbedder,
    from_env,
)


def test_embedder_protocol_has_required_methods():
    # Protocol classes don't have hasattr returning True for abstract methods
    # unless they're declared. Use inspect to check the protocol's members.
    from devmanager_llm.embedder import Embedder  # noqa: F811

    members = {"embed", "dimensions"}
    assert members.issubset(set(dir(Embedder)))


def test_openai_default_model():
    e = OpenAIEmbedder()
    assert e.model == "text-embedding-3-small"
    assert e.dimensions == 1536


def test_azure_requires_deployment_and_base():
    with pytest.raises(ValueError):
        AzureOpenAIEmbedder(deployment="", api_base="")
    e = AzureOpenAIEmbedder(deployment="my-dep", api_base="https://x.openai.azure.com")
    assert e.dimensions > 0


def test_ollama_default_model():
    e = OllamaEmbedder(base_url="http://localhost:11434")
    assert e.model == "nomic-embed-text"
    assert e.dimensions == 768


# --- Mock-based dispatch tests (Task 3.2 content, include now for completeness) ---


@pytest.mark.asyncio
async def test_openai_embed_dispatches_httpx(monkeypatch):
    captured: dict = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [0.1, 0.2, 0.3]}]}

    async def fake_post(self, url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs.get("json")
        return FakeResp()

    import httpx

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    e = OpenAIEmbedder(api_key="test-key")
    out = await e.embed(["hello"])
    assert out == [[0.1, 0.2, 0.3]]
    assert captured["json"]["model"] == "text-embedding-3-small"
    assert captured["url"] == "https://api.openai.com/v1/embeddings"


@pytest.mark.asyncio
async def test_azure_embed_dispatches_httpx(monkeypatch):
    captured: dict = {}

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"data": [{"embedding": [0.4, 0.5]}]}

    async def fake_post(self, url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        captured["json"] = kwargs.get("json")
        return FakeResp()

    import httpx

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    e = AzureOpenAIEmbedder(deployment="dep1", api_base="https://x.openai.azure.com", api_key="k")
    out = await e.embed(["hi"])
    assert out == [[0.4, 0.5]]
    assert "deployments/dep1/embeddings" in captured["url"]
    assert captured["params"] == {"api-version": "2024-02-01"}


@pytest.mark.asyncio
async def test_ollama_embed_dispatches_httpx(monkeypatch):
    captured: list = []

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"embedding": [0.7, 0.8, 0.9]}

    async def fake_post(self, url, **kwargs):
        captured.append({"url": url, "json": kwargs.get("json")})
        return FakeResp()

    import httpx

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    e = OllamaEmbedder(base_url="http://localhost:11434")
    out = await e.embed(["a", "b"])
    assert out == [[0.7, 0.8, 0.9], [0.7, 0.8, 0.9]]
    assert len(captured) == 2
    assert captured[0]["url"] == "http://localhost:11434/api/embeddings"


# --- from_env factory tests (Task 3.3 content) ---


def test_from_env_openai(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    e = from_env()
    assert isinstance(e, OpenAIEmbedder)


def test_from_env_azure(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "azure")
    monkeypatch.setenv("AZURE_EMBEDDING_DEPLOYMENT", "dep")
    monkeypatch.setenv("AZURE_OPENAI_API_BASE", "https://x.openai.azure.com")
    e = from_env()
    assert isinstance(e, AzureOpenAIEmbedder)


def test_from_env_ollama(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")
    e = from_env()
    assert isinstance(e, OllamaEmbedder)
    assert e.model == "nomic-embed-text"
