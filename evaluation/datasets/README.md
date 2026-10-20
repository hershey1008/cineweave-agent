# Evaluation input status

- `retrieval_queries.jsonl`: 120 query drafts, 60 development / 60 test. Written as evaluation inputs, **not yet human reviewed or relevance annotated**. Review intent-family leakage before treating the split as sealed.
- `conversation_cases.json`: 40 three-turn rule-mode functional fixtures. They measure constraint/state behavior, not human satisfaction or LLM generalization.
- `relevance_labels.example.tsv`: schema-only header. Supply independently reviewed grades 0/1/2 and annotator IDs before computing retrieval quality.
- Additional edge, isolation, replay and concurrency scenarios are covered by integration tests.

Reports must distinguish deterministic unit tests, live rule-mode conversations, real LLM tests, and human relevance evaluations. Empty qrels cannot produce benchmark claims.
