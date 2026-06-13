from devmanager_agents.chunker import Chunk, ChunkStrategy, HybridChunker


def test_chunk_strategy_values():
    assert ChunkStrategy.MARKDOWN_HEADING.value == "md_heading"
    assert ChunkStrategy.CODE_FUNCTION.value == "code_function"
    assert ChunkStrategy.PARAGRAPH.value == "paragraph"
    assert ChunkStrategy.TOKEN_CAP.value == "token_cap"


def test_chunk_dataclass():
    c = Chunk(content="hello", token_count=1, metadata={"src": "x"})
    assert c.content == "hello"
    assert c.token_count == 1
    assert c.metadata == {"src": "x"}


def test_token_cap_splits_long_text():
    text = " ".join(f"word{i}" for i in range(1000))  # ~1000 tokens
    c = HybridChunker(
        max_tokens=200,
        overlap_tokens=20,
        primary=ChunkStrategy.TOKEN_CAP,
        fallback=ChunkStrategy.TOKEN_CAP,
    )
    chunks = c.chunk(text, file_type="other")
    assert len(chunks) > 1
    assert all(ch.token_count <= 220 for ch in chunks)  # 容许 overlap 上浮


def test_short_text_returns_single_chunk():
    text = "short text"
    c = HybridChunker(
        max_tokens=800,
        overlap_tokens=100,
        primary=ChunkStrategy.TOKEN_CAP,
        fallback=ChunkStrategy.TOKEN_CAP,
    )
    chunks = c.chunk(text, file_type="other")
    assert len(chunks) == 1
    assert chunks[0].content == "short text"


def test_paragraph_splits_on_double_newline():
    text = "para1.\n\npara2.\n\npara3."
    c = HybridChunker(
        max_tokens=800,
        overlap_tokens=0,
        primary=ChunkStrategy.PARAGRAPH,
        fallback=ChunkStrategy.TOKEN_CAP,
    )
    chunks = c.chunk(text, file_type="txt")
    contents = [ch.content for ch in chunks]
    assert contents == ["para1.", "para2.", "para3."]


def test_markdown_heading_splits_at_h2():
    text = "# H1\n\nintro\n\n## H2-A\n\nbody A\n\n## H2-B\n\nbody B"
    c = HybridChunker(
        max_tokens=800,
        overlap_tokens=0,
        primary=ChunkStrategy.MARKDOWN_HEADING,
        fallback=ChunkStrategy.TOKEN_CAP,
    )
    chunks = c.chunk(text, file_type="md")
    contents = [ch.content for ch in chunks]
    # 期待：["# H1\n\nintro", "## H2-A\n\nbody A", "## H2-B\n\nbody B"]
    assert len(contents) == 3
    assert contents[0].startswith("# H1")
    assert "H2-A" in contents[1] and "body A" in contents[1]
    assert "H2-B" in contents[2] and "body B" in contents[2]


def test_code_function_splits_python():
    text = "import os\n\ndef foo():\n    return 1\n\ndef bar():\n    return 2\n"
    c = HybridChunker(
        max_tokens=800,
        overlap_tokens=0,
        primary=ChunkStrategy.CODE_FUNCTION,
        fallback=ChunkStrategy.TOKEN_CAP,
    )
    chunks = c.chunk(text, file_type="py")
    contents = [ch.content for ch in chunks]
    assert any("def foo" in x for x in contents)
    assert any("def bar" in x for x in contents)


def test_hybrid_falls_back_to_token_cap_for_oversized_chunk():
    # 制造一个超长 paragraph，触发 fallback
    text = "w " * 2000
    c = HybridChunker(
        max_tokens=100,
        overlap_tokens=10,
        primary=ChunkStrategy.PARAGRAPH,
        fallback=ChunkStrategy.TOKEN_CAP,
    )
    chunks = c.chunk(text, file_type="txt")
    assert len(chunks) > 1
    assert all(ch.token_count <= 110 for ch in chunks)
