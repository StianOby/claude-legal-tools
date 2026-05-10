# Zotero SQL — Norwegian case law

**Hyphens in case numbers:** court PDFs (and Lovdata print format) often render the hyphens in case numbers as U+2011 NON-BREAKING HYPHEN rather than ASCII U+002D, to keep the number from breaking across lines. A `LIKE '%HR-2018-456%'` pattern with regular hyphens will silently miss these. The templates below use `%` as the separator, which matches both. Always read the `snippet` to rule out false positives.

```sql
-- For a modern HR case (e.g. HR-2018-456-P Nesseby):
SELECT ri.id, ri.title, ri.authors, SUBSTR(d.content, 1, 400) AS snippet
FROM reference_items ri
JOIN documents d ON d.reference_id = ri.id AND d.kind = 'fulltext_chunk' AND d.chunk_index = 0
WHERE d.content LIKE '%HR%2018%456%'   -- add OR d.content LIKE '%Nesseby%' if unsure of number
LIMIT 5;

-- For an older Rt. case (e.g. Rt. 20