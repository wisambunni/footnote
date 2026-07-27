---
name: rag-pipeline
description: Designs and hardens production-grade retrieval-augmented generation systems — ingestion, chunking, embedding, retrieval, reranking, generation, and evaluation. Use when building a RAG pipeline, debugging poor answer quality, choosing a vector store or embedding model, or deciding whether retrieval quality is good enough to ship.
---

# RAG pipeline

Build retrieval that a generation model can trust. Most RAG failures are
retrieval failures wearing a generation costume — the model answered faithfully
from context that was wrong, incomplete, or absent. Fix retrieval first.

Work backward from evaluation. A pipeline you cannot measure is a pipeline you
cannot improve, and every decision below (chunk size, model, top-k, reranking)
is a knob you tune against a metric, not a thing you get right by taste.

## Establish evaluation before building

Before writing ingestion code, build a golden set: 30–100 real questions paired
with the passages that should answer them and the answer a human would accept.
Draw questions from actual or anticipated user queries, not ones invented to
match the corpus. This set is the contract every later change is tested against.

Separate the two failure surfaces and measure them independently:

- **Retrieval** — did the right chunks come back? Recall@k (is the gold passage
  in the top k?) and MRR (how high?). If recall@k is low, no amount of prompt
  engineering saves you.
- **Generation** — given correct context, is the answer faithful and complete?
  Faithfulness (every claim traceable to context — this is where hallucination
  hides) and answer relevance. Use an LLM judge with a rubric, but validate the
  judge against human labels on a sample before trusting it.

Track retrieval and generation metrics on every change. A "better" embedding
model that raises recall but a reranking change that quietly drops it will look
like progress in aggregate and be a regression in production.

## Ingestion and chunking

Chunking is the highest-leverage and most under-attended decision. The unit you
index is the unit you retrieve — get it wrong and everything downstream inherits
the error.

- **Chunk on structure, not character count.** Split on semantic boundaries —
  headings, sections, paragraphs, code blocks, table rows — then pack to a size
  budget. A fixed 512-token window that cuts mid-sentence or splits a table from
  its header destroys the meaning you are trying to retrieve.
- **Size to the answer, not a default.** If answers live in a sentence, small
  chunks retrieve precisely. If they need surrounding context, chunk larger or
  retrieve neighbors. Start ~256–512 tokens with ~10–20% overlap and tune
  against the golden set — do not cargo-cult a number.
- **Attach metadata at ingest** — source, section title, page, timestamp,
  permissions/tenant, version. You need it for filtering, citations, access
  control, and incremental re-indexing, and you cannot reconstruct it later.
- **Consider what you embed vs. what you return.** Embed a small, dense unit for
  retrieval precision; return an expanded window (parent doc, neighboring
  chunks) for generation completeness. "Small-to-big" / parent-document
  retrieval fixes most "right chunk, not enough context" failures.
- **Make ingestion idempotent and incremental.** Content-hash chunks so re-runs
  don't duplicate, and re-index only what changed. A pipeline that only supports
  full rebuilds becomes unshippable the moment the corpus is large or live.

## Embedding and the vector store

- **Choose the embedding model against your golden set, not a leaderboard.**
  Leaderboards measure a different corpus. Weigh domain fit, dimension (storage
  and latency cost), max sequence length (must exceed your chunk size), and
  whether it's multilingual if you are. Version the model — changing it means
  re-embedding everything, so store which model produced each vector.
- **The vector store choice is mostly an ops choice.** pgvector if you already
  run Postgres and want one system of record with transactional metadata;
  a dedicated store (Qdrant, Weaviate, Milvis-class) when scale, filtering, or
  hybrid features justify a second system. Do not add infrastructure a JOIN
  would have solved.
- **Metadata filtering must be first-class.** Pre-filter by tenant, permission,
  recency, and source at query time. Post-filtering after top-k silently starves
  results — you ask for 10 and get 2 after the permission filter. Filter in the
  query.

## Retrieval

- **Hybrid beats pure vector for most corpora.** Dense embeddings miss exact
  terms — names, error codes, SKUs, acronyms, rare jargon. Combine dense with
  sparse/keyword (BM25) and fuse (reciprocal rank fusion is a strong,
  parameter-light default). This single change fixes a large class of "obvious
  query returned nothing" bugs.
- **Retrieve wide, then rerank narrow.** Pull top ~50–100 candidates, rerank
  with a cross-encoder, keep the top ~3–8 for the prompt. A cross-encoder scores
  query and passage jointly and is far more accurate than embedding cosine — it
  is the highest-ROI addition to a naive pipeline. Budget the extra latency.
- **Transform the query when it helps.** Multi-query (generate paraphrases and
  union results) raises recall on underspecified questions; HyDE (embed a
  hypothetical answer) helps when questions and documents use different
  vocabulary. Both cost a model call — measure that they earn it.
- **Right-size top-k.** Too few starves the answer; too many buries the signal
  and wastes context budget and money. Tune k against generation faithfulness,
  not intuition — more context is not more better.

## Generation

- **Ground hard and cite.** Instruct the model to answer only from context and
  to say when the context is insufficient. Require citations to chunk IDs so
  every claim is auditable and users can verify — citations are a feature and a
  guardrail at once.
- **Give the model an escape hatch.** "I don't know" from empty or weak
  retrieval is correct behavior, not failure. A pipeline that forces an answer
  when retrieval returned nothing is a hallucination generator.
- **Order context deliberately.** Models weight the start and end of long
  contexts more than the middle. Place the strongest reranked passages at the
  edges; don't dump 8 chunks in arbitrary order.
- **Watch the context budget.** Reranked-narrow keeps prompts lean. If you are
  stuffing context to the model's limit you have a retrieval precision problem,
  not a context-window problem — fix upstream.

## Production concerns

- **Cache deliberately.** Cache embeddings (deterministic per model+text) always.
  Cache full responses for repeated queries only if the corpus is stable, and
  invalidate on re-index or the cache serves stale answers with confidence.
- **Log the whole trace.** Query, retrieved chunk IDs and scores, rerank scores,
  final prompt, response, latency per stage. When an answer is wrong you must be
  able to tell whether retrieval or generation failed — without the trace you
  are guessing.
- **Handle the corpus lifecycle.** Documents change, expire, and get deleted.
  Deleted source content must leave the index or you leak and cite stale or
  unauthorized data. Version and re-index; treat the index as a derived,
  rebuildable artifact.
- **Enforce access control at retrieval.** Filter by the requesting user's
  permissions in the query itself. RAG that retrieves across tenants is a data
  breach, and it is invisible until someone sees another tenant's document in a
  citation.
- **Budget cost and latency per stage.** Embedding, retrieval, reranking, and
  generation each add both. Know the per-query cost and the p95 latency, and
  which stage dominates, before scaling — the reranker or a multi-query
  expansion is often the hidden cost center.

## Debugging poor quality

Localize before fixing. Take failing questions from the golden set and check, in
order: was the gold passage even ingested and indexed? Did retrieval return it
in the top-k (recall)? Did reranking keep it or bury it? Given correct context,
did generation use it faithfully? The fix is entirely different at each stage,
and skipping the localization is why RAG debugging so often turns into prompt
roulette.

## Output

Lead with the diagnosis or the recommended architecture, not preamble. When
proposing a pipeline, state the choices and the tradeoff behind each, and name
the metric each choice should be tuned against. Flag decisions being made on
taste that should be made on the golden set — the most common failure is
shipping a pipeline nobody measured.
