# Phase II, Chunk 1: assessment history and deltas

This chunk adds a presentation-independent historical model and delta engine. It does not
alter the Phase I report workflow, percentile logic, PDF design, or email behavior.

Assessment dates come from hardware export column 10, the existing assessment/session
timestamp. Its calendar date is normalized and attempts are selected independently within
each athlete/date group by the validated Phase I rules.

Current data limitations:

- The juggling CSV has only `First Name`, `Last Name`, `Dominant`, `Non-Dominant`, and
  `Thighs`; it contains no reliable assessment date. Undated scores remain usable for an
  athlete with one hardware assessment, but are deliberately not copied to any of multiple
  historical assessments. The model can hold dated juggling metrics when a dated source is
  supplied later.
- Age group comes from the current roster. The sources do not provide a reliable historical
  age group for each assessment, so historical age groups are not inferred.

Run `python -m src.phase2_audit` to write the real-data history and delta audits beneath
`output/phase2/debug/`.
