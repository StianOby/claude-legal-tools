# Zotero SQL — Norwegian preparatory works

Recommended query pattern (adapt year, document number, and authors to the reference you are looking up):

```sql
-- For Ot.prp./Prop. L/St.prp. (ministry-authored):
SELECT ri.id, ri.title, ri.year, ri.authors,
       d.content
FROM reference_items ri
JOIN documents d ON d.reference_id = ri.id AND d.kind = 'fulltext_chunk'
WHERE ri.year IN ('1998', '1999')          -- both years of the session designation
  AND d.chunk_index = 0                    -- citation number appears in first chunk
  AND ri.authors LIKE '%departement%'
  AND d.content LIKE '%nr. 3%'             -- document number from the citation
ORDER BY ri.id
LIMIT 5;

-- For NOU (committee-authored — departement filter does NOT apply):
SELECT ri.id, ri.title, ri.year, ri.authors,
       d.content
FROM reference_items ri
JOIN documents d ON d.reference_id = ri.id AND d.kind = 'fulltext_chunk'
WHERE ri.year IN ('2022')
  AND d.chunk_index = 0
  AND d.content LIKE '%NOU 2022:%8%'       -- tighter pattern avoids e.g. NOU 2022:18
ORDER BY ri.id
LIMIT 5;

-- For Innst. (committee recommendation — committee-authored, like NOUs):
SELECT ri.id, ri.title, ri.year, ri.authors,
       d.content
FROM reference_items ri
JOIN documents d ON d.reference_id = ri.id AND d.kind = 'fulltext_chunk'
WHERE ri.year IN ('1961', '1962')
  AND d.chunk_index = 0
  AND ri.authors LIKE '%komite%'
  AND d.content LIKE '%Innst%nr. 49%'      -- include "Innst" to avoid false matches
ORDER BY ri.id
LIMIT 5;
```
