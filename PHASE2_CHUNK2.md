# Phase II, Chunk 2: historical comparison rendering

Page 3 is appended only when an athlete has at least two genuine dated assessments. It
compares the latest assessment with the immediately preceding assessment. One-assessment
athletes retain the approved two-page report; no empty Page 3 is produced.

Page 3 presents raw Previous, Current, direction-aware Change, and Status values for all ten
metrics. It does not contain a historical radar. Historical percentile context would be
misleading because historical cohorts and age groups cannot currently be reconstructed, and
raw metric units are incompatible across radar axes.

The current roster remains authoritative for the displayed current team and age group. No
historical team or age group is inferred. The current juggling source is undated, so its
values are never copied backward or across multiple assessment dates. Juggling comparisons
require genuine values on both dated assessment objects.

The real production dataset currently has zero Page 3-eligible athletes. Files prefixed
`TEST_DEBUG_` in `output/phase2/debug/progress_previews/` are synthetic visual fixtures only;
they are not production data and are never written into the production report directory.
