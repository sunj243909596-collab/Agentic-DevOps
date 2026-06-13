-- migrations/postgres/013_team_ops_knowledge.sql
-- Phase 7.4: Knowledge Base — pgvector-backed semantic search over RAG chunks.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE knowledge_document (
    document_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source         TEXT NOT NULL,
    title          TEXT NOT NULL,
    repository     TEXT,
    file_path      TEXT,
    language       TEXT,
    version        TEXT,
    metadata       JSONB NOT NULL DEFAULT '{}',
    indexed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (source, title, version)
);

CREATE TABLE knowledge_chunk (
    chunk_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id    UUID NOT NULL REFERENCES knowledge_document(document_id) ON DELETE CASCADE,
    chunk_index    INTEGER NOT NULL,
    content        TEXT NOT NULL,
    embedding      vector(1536),
    token_count    INTEGER NOT NULL,
    metadata       JSONB NOT NULL DEFAULT '{}',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_id, chunk_index)
);

CREATE INDEX idx_chunk_embedding ON knowledge_chunk
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_chunk_doc ON knowledge_chunk(document_id);

-- settings 表插入默认值
INSERT INTO settings (key, value) VALUES
    ('kb_min_similarity', '0.7'),
    ('kb_top_k', '5')
ON CONFLICT (key) DO NOTHING;
