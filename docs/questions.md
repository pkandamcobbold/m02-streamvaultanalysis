# Questions for the client

Findings we could not settle ourselves. A data engineer decides how to handle data; the business
decides what it means. Each question shows the evidence, the options, and what we would recommend,
so it could be answered in one reply.

**The thing to know about this table.** Kwame Boateng was explicitly unavailable before the board
review on 31 October, and the brief says so: *"Where the brief doesn't settle something, decide it,
and say what you decided."* So most of the rows below were never answered by anyone. We asked them,
recorded them, decided, and carried the cost of being wrong in the ADR. The **Answer** column says
`Not available` where that happened — which is a different fact from a question nobody thought to
ask, and the distinction is the point of keeping the table.

Questions Q8 to Q12 were genuinely ambiguous about the *work* rather than the business, and were
settled with the module reviewer.

| ID | When | To | Finding | Question | Answer | What we did |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | Investigation | Kwame / the acquisition team | F8, F12 | What is "performance" for a licensing decision? Box-office return on budget, total revenue, audience rating, or audience size? We would use return on budget plus an audience measure, never a single number. | Not available | Return on budget as the primary measure, with revenue, rating and vote count reported beside it. Never one metric alone (ADR-019) |
| Q2 | Investigation | Kwame / the acquisition team | F7 | 9 of the 112 films are the only member of their collection on your list. Is a one-film collection a franchise for buying purposes? We would say no — there is no bundle to sell — but they are not ordinary standalones either. | Not available | Three categories, with the threshold in settings and the headline reported both ways (ADR-010) |
| Q3 | Investigation | Kwame / Finance | F12 | What counts as a hit? We suggest 2.5× budget, roughly theatrical break-even. Note that 92% of your list clears it, because nothing on the list ever lost money. | Not available | Kept 2.5 for its external justification and reported two relative definitions beside it (ADR-015) |
| Q4 | Investigation | Kwame / Finance | F8 | If a film showed a budget or box office of zero, would you read that as a real figure of nothing or as a gap in the record? We would treat it as a gap. | Not available | Treated as a gap, behind a setting that runs it the other way. Moot this quarter: no zeros exist (ADR-017) |
| Q5 | Investigation | Yaw / Finance | F10 | Pre-2000 budgets and box office are in the dollars of their year, and an old film's takings keep accruing through re-releases. Should we adjust to constant dollars, or report the two eras separately and never compare a level across them? | Not available | Reported separately, with rank-based measures. No CPI adjustment: it needs data the brief does not provide and would not fix the re-release problem (ADR-013) |
| Q6 | Investigation | The negotiators | F9 | Who is "the lead actor" — the top-billed name only, or the top three? And when two people co-direct, whose record is it? | Not available | Top-billed as the lead, with a top-3-billed view as a published sensitivity. A co-directed film counts for both directors (ADR-012) |
| Q7 | Investigation | The negotiators | — | How many films should someone have before you would use their name as a lever? We suggest three, and we will print the film count beside every name regardless. | Not available | Three, as a filter on the *recommendation* and never on the table. One wiring of this changed the reliable-actor count from 19 to 44 (ADR-030) |
| Q8 | Build | Module reviewer | — | Is there a stated time budget for the analysis stages? The pipeline guide mentions "the client's time budget"; the brief names no number. | None given — ours to set and state | 10s for the analysis stages, warm cache, acquisition excluded, boundary stated in the memo. Measured 1.9s (ADR-023) |
| Q9 | Build | Module reviewer | — | Where is `id_list.csv`? It is referenced but not in the repository. | Given with the lab | Downloaded to `data/input/id_list.csv`, committed, never edited |
| Q10 | Build | Module reviewer | — | What are the "four slices" for the spot-check? Is franchise/standalone × pre/post-2000 what is meant? | Ours to choose | Four slices chosen to match the findings: shortlisted, flagged extreme, pre-2000, random control (ADR-026) |
| Q11 | Build | Module reviewer | — | Is a notebook, scripts, or both expected for the "working analysis"? | Both | Logic in `pipeline/`, `explore/analysis.ipynb` as the narrative that imports it, `run_pipeline.py` as the one command (ADR-027, ADR-032) |
| Q12 | Build | Module reviewer | — | The board review is 31 October. What as-of date should the memo carry — the review date, the day it was written, or the date of the data? | The date of the data | The `fetched_at` stamp carried in the cached envelopes, not today's date. The two differ as soon as a run reads from cache, which is the normal case |
| Q13 | Acquisition | TMDb / the three source desks | F6 | Five ids return 404, and every one is above 7.7 million while every working id is below 302,000. Were these ever films, and can the original rows be recovered? | Not available | Recorded as permanently unavailable. TMDb never reissues ids, so there is nothing to resolve and no title to search for (ADR-007) |
| Q14 | Acquisition | The three source desks | F6, F3 | Which desk produced the ids above 7.7 million, and which produced the IMDb id? If one batch is unreliable we would weight its rows differently. | Not available | Nothing done: with no provenance per row, the losses cannot be tested for era or group bias. Stated as a limit in the memo (ADR-007) |
| Q15 | Build | Kwame / Finance | F8, F19 | Above what share of missing money data should we publish nothing rather than a partial number? We suggest 20%. And should a live re-check that moves the answer block publication? | Not available | 20%, and yes. Both are gate checks, with the overriding setting named in the failure message (ADR-029) |

## What we would ask next quarter

Three of these stop being hypothetical once Adjoa reruns this against ~500 titles:

- **Q2 again.** If the lone-collection-member group does not shrink proportionally, the list is
  being assembled by picking single entries out of franchises, which is worth telling Kwame
  directly rather than handling as a grouping decision.
- **Q3 again.** The hit threshold is uninformative on a list with no failures in it (F12). A larger
  list will probably contain films that lost money, at which point the threshold deserves to be set
  against that distribution.
- **Q14, with an answer attached.** If the candidate list arrives with a source column — which desk
  each row came from — the loss analysis in F6 becomes testable instead of a stated limit. That is
  worth asking for before the file is assembled, not after.
