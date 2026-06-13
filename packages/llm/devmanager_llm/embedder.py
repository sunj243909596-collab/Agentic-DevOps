from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


@runtime_checkable
class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    def dimensions(self) -> int: ...


class OpenAIEmbedder:
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        *,
        api_key: str | None = None,
    ) -> None:
        self.model = model
        self._api_key: str = api_key if api_key else os.getenv("OPENAI_API_KEY", "")
        self._dim_map = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }

    @property
    def dimensions(self) -> int:
        return self._dim_map.get(self.model, 1536)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"input": texts, "model": self.model},
            )
            r.raise_for_status()
            data = r.json()
            return [d["embedding"] for d in data["data"]]


class AzureOpenAIEmbedder:
    def __init__(
        self,
        deployment: str,
        api_base: str,
        *,
        api_key: str | None = None,
        api_version: str = "2024-02-01",
    ) -> None:
        if not deployment or not api_base:
            raise ValueError("deployment and api_base required")
        self.deployment = deployment
        self.api_base = api_base.rstrip("/")
        self.api_version = api_version
        self._api_key: str = api_key if api_key else os.getenv("AZURE_OPENAI_API_KEY", "")

    @property
    def dimensions(self) -> int:
        return 1536

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        url = f"{self.api_base}/openai/deployments/{self.deployment}/embeddings"
        params = {"api-version": self.api_version}
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                url,
                params=params,
                headers={"api-key": self._api_key, "Content-Type": "application/json"},
                json={"input": texts},
            )
            r.raise_for_status()
            data = r.json()
            return [d["embedding"] for d in data["data"]]


class OllamaEmbedder:
    def __init__(self, base_url: str, model: str = "nomic-embed-text") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    @property
    def dimensions(self) -> int:
        return 768

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import httpx

        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=30) as client:
            for t in texts:
                r = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": t},
                )
                r.raise_for_status()
                out.append(r.json()["embedding"])
        return out


def from_env() -> Embedder:
    """Factory: dispatch by EMBEDDING_PROVIDER env var (openai|azure|ollama)."""
    provider = os.getenv("EMBEDDING_PROVIDER", "openai").lower()
    if provider == "azure":
        return AzureOpenAIEmbedder(
            deployment=os.getenv("AZURE_EMBEDDING_DEPLOYMENT", ""),
            api_base=os.getenv("AZURE_OPENAI_API_BASE", ""),
        )
    if provider == "ollama":
        return OllamaEmbedder(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"),
        )
    return OpenAIEmbedder(model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small"))
