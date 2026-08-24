from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from footnote.db.base import Base

# Dimension of the embedding model. Changing models almost always changes this,
# which is a destructive column change *and* forces re-embedding every chunk —
# so treat it as a schema-level decision, not a config knob.
EMBEDDING_DIM = 384


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    cik: Mapped[str]
    company_name: Mapped[str]
    accession_no: Mapped[str] = mapped_column(unique=True)
    form_type: Mapped[str] = mapped_column(default="10-K")
    fiscal_year: Mapped[int | None]
    filing_date: Mapped[date]
    source_url: Mapped[str | None]
    content_hash: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # "Apple's FY2023 10-K" is the shape of nearly every lookup and every
    # retrieval-time metadata filter, so index it rather than scanning.
    __table_args__ = (Index("ix_documents_cik_fiscal_year", "cik", "fiscal_year"),)

    def __repr__(self) -> str:
        return f"<Document {self.company_name} {self.fiscal_year} ({self.accession_no})>"


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    item_number: Mapped[str | None]
    section_title: Mapped[str | None]
    chunk_index: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # Which model produced `embedding`. Without this you cannot tell a re-embedded
    # row from a stale one, and a half-migrated table silently mixes vector spaces.
    embedding_model: Mapped[str | None]

    # Postgres maintains this from `content` on every insert/update. A generated
    # column can't drift the way an application-maintained one does when some
    # code path forgets to refresh it.
    tsv: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', content)", persisted=True),
    )

    __table_args__ = (
        # Re-ingesting a filing should update chunks in place, not duplicate them.
        UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_chunk_index"),
        # Sparse half of hybrid retrieval: keyword/BM25-style matching.
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
        # Dense half: approximate nearest neighbour. Cosine ops must match the
        # distance operator queries use (<=>), or the planner ignores the index.
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    def __repr__(self) -> str:
        return f"<Chunk doc={self.document_id} #{self.chunk_index} {self.item_number}>"
