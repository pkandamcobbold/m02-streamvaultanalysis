# Data findings — StreamVault



## Summary

I pulled 127 candidate titles from the list, got usable data for 112, and found eleven things that
change what Kwame should do with the $14M or how much he should trust the answer.

Six of them are high severity, and the first three are not faults in the data at all. They are
limits on what this list can tell anyone. The candidate list contains no film that lost money, so
the central argument about franchises being the safer buy cannot be tested here. The gap between
the two groups is small enough that once films in the same franchise stop counting as independent
results, no single measure of it survives resampling. And the ordinary choice of statistic — the
average — reverses the recommendation.

The other three high-severity findings are about comparability. Most of the list belongs to a franchise, money from the 1970s cannot be compared with money from the 2010s, and every exceptional
return on the list is an old film, so the usual habit of trimming outliers would quietly delete a
fifth of the pre-2000 evidence and none of the modern.

Five medium-severity findings follow. Two qualify the recommendation — one of them removes a
discount argument the team expected to use. Three are traps in the source data where the obvious
handling is wrong and leaves no trace in the output.

I would still recommend franchise bundles over standalone titles — on the agreement between four
measures, all of which point the same way, rather than on any one of them. No single gap clears
zero on this sample. F-02 is why, and it is the first thing I would expect to be asked about.

## Reconciliation

| Stage | Rows | Delta | Reason |
|---|---|---|---|
| `id_list.csv`, as received | 128 | — | lines in the file |
| Header removed | 127 | −1 | `tmdb_id` on line 1 |
| Duplicate ids set aside | 121 | −6 | same TMDb id as an earlier row (rows 43, 60, 90, 91, 94, 102) |
| Unusable values set aside | 118 | −3 | `-1` at row 30, `N/A` at row 111, one blank row |
| Cross-namespace duplicate set aside | 117 | −1 | an IMDb id that resolves to a film already listed twice (F-09) |
| Fetched from TMDb | 112 | −5 | five ids return 404 (F-10) |
| Reached the analysis table | 112 | 0 | every film fetched is in the analysis |
| Usable in the money metrics | 112 | 0 | no film is missing a budget or a box-office figure |

**127 received, 112 analysed, 15 set aside.** Seven of the fifteen are not losses: six duplicates
and one cross-namespace duplicate are films already counted among the 112, and removing them
prevents double-counting. The genuine losses are eight rows: five dead ids, two placeholders and a
blank row. So Kwame is deciding on 112 titles rather than 120, a 6.7% reduction.

Every row of this table can be rebuilt from `data/processed/id_ledger.csv`, which keeps one row per
line of the source file and a reason on every row that did not make it.

---

## Findings, ranked by risk

### F-01: The list contains no film that lost money — Severity: High

- **What it is:** Not one of the 112 films returned less than its budget. The worst performer on
  the whole list made back 1.13 times what it cost.
- **How I detected it:** I looked at the minimum return in each group while profiling, expecting a
  spread that included failures. There were none to find.
- **Scale:** All 112 films. The flag I built to catch a film whose revenue fell below its budget
  never fires.
- **Effect on the client's number:** Half of Kwame's team believes franchise bundles are the safer
  buy. Safety is a claim about what happens when a film fails, and there are no failures here to
  compare. The claim cannot be tested on this list, in either direction. It also explains why the
  break-even hit rate barely separates the groups: 92% of the list clears it, so the measure has
  almost nothing to discriminate between.
- **What I did about it:** I report the hit rate alongside two relative definitions rather than
  leading with it, and I say in the memo that the downside argument is unproven either way. I did
  not raise the hit threshold to make the numbers look more interesting, because a threshold chosen
  after seeing its effect cannot survive the question "why that number?".
- **Residual risk:** The list was assembled by three desks over four years, and nobody kept the
  titles they rejected. If weak films were filtered out before the list reached us — which this
  pattern strongly suggests — then every performance figure here is measured on survivors, and the
  whole analysis is about which of these films to buy rather than about what the market looks like.
  I cannot correct for that with the data I have.

---

### F-02: No single measure of the headline gap survives resampling — Severity: High

- **What it is:** The comparison the memo leads with is a typical return of 5.53 for franchise films
  against 5.00 for standalone titles. That difference is too small for this sample to establish.
- **How I detected it:** I resampled the cleaned table and looked at the spread of the gap on every
  measure the memo could lead with. Then I did it again resampling whole franchises rather than
  individual films, because films in the same franchise are not independent observations and
  treating 87 of them as 87 results overstates the evidence.
- **Scale:** The whole comparison. 87 franchise films and 25 standalones, and the 87 come from only 23 collections.

  Resampling individual films, 10,000 draws:

  | Measure | Gap | 95% interval | Franchise ahead | Excludes zero |
  |---|---|---|---|---|
  | Typical return (median) | +0.53 | −6.29 to +3.08 | 0.81 | no |
  | Weaker end (lower quartile) | +1.27 | −0.69 to +2.57 | 0.93 | no |
  | Share clearing break-even | +0.15 | +0.006 to +0.33 | 0.98 | **yes** |
  | Spread (narrower is better) | −7.33 | −12.20 to +1.88 | 0.89 | no |

  Resampling the 23 whole franchises instead, 2,000 draws — the honest unit, because films in one
  franchise share a cast, a director, an audience and a marketing budget:

  | Measure | Gap | 95% interval | Franchise ahead | Excludes zero |
  |---|---|---|---|---|
  | Typical return | +0.53 | −6.24 to +3.18 | 0.79 | no |
  | Weaker end | +1.27 | −0.63 to +2.61 | 0.94 | no |
  | Share clearing break-even | +0.15 | −0.001 to +0.32 | 0.97 | no |
  | Spread | −7.33 | −17.72 to +1.92 | 0.89 | no |

- **Effect on the client's number:** Once sequels stop being counted as independent results,
  **no single measure's gap excludes zero** — the break-even share, the one that held per film,
  crosses it by a thousandth. The honest statement is therefore not "franchise films return more"
  but "franchise films are the more likely bet on all four measures, and on this list no one
  measure settles it alone". That is a weaker claim than the memo made in its first draft and a
  defensible one, and it is the agreement across measures — four out of four, 78% to 97% of draws —
  that carries the recommendation, not any single interval.
- **What I did about it:** `pipeline/transform/uncertainty.py` computes both, publishes
  `kpi_uncertainty.csv` and `kpi_uncertainty_by_franchise.csv`, and prints which measures survive
  and which are lost to clustering. The memo's limitations section states the result in those
  terms. The seed is in `settings.toml`, so a reviewer who re-runs gets the same intervals and can
  tell a real change from a new draw (M14).
- **Residual risk:** This is still the finding most likely to be raised in the room, and the answer
  to "is 5.5 against 5.0 a real difference?" is "not on 25 standalones, no". What survives is the
  direction and its consistency. A reader who wants a single number with a tight interval will not
  get one from this sample, and the memo does not offer one.

---

### F-03: The mean and the median disagree about who wins — Severity: High

- **What it is:** Averages say buy standalone titles. Typical films say buy franchise bundles. Mean return is
  10.48 for standalones against 7.94 for franchise; median return is 5.53 for franchise against 5.00 for
  standalones.
- **How I detected it:** I computed both and compared them, rather than picking one.
- **Scale:** The whole comparison. Three of the 25 standalone films are exceptional performers against
  five of the 87 franchise films, so the smaller group's average is pulled much further by them.
- **Effect on the client's number:** It reverses the recommendation. On averages the memo would
  advise cherry-picking standalone hits, and the case would rest on *Jaws*, *The Good, the Bad and the
  Ugly* and *Pulp Fiction* — films from 1975, 1966 and 1994 whose returns nothing available today
  can repeat.
- **What I did about it:** I report medians and quartiles, with the mean printed beside them so the
  disagreement is visible rather than buried, and the memo discloses the reversal without being
  asked. Spread is the interquartile range rather than the standard deviation, for the same reason:
  one 70-times return inflates a standard deviation without saying anything about the typical gap
  between a good and a bad film.
- **Residual risk:** The median throws away information about upside, and upside is part of an
  acquisition case. A buyer who wants one spectacular title rather than a reliable slate is served
  better by the average. I give that reader the maximum and the full shortlist rather than arguing
  with them.

---

### F-04: The standalone group is 16 films — Severity: High

- **What it is:** The brief asks for a two-way comparison, but the data has three groups. 96 of the
  112 films belong to a franchise. Nine of those are the only film of their collection on the candidate
  list, which makes them neither a bundle Kwame can buy nor an ordinary standalone title. That leaves
  16 true standalones.
- **How I detected it:** I counted how many films from each collection are actually on the list, rather
  than assuming that belonging to a collection meant a bundle was on offer.
- **Scale:** 87 franchise films, 9 lone members, 16 true standalones. Under the grouping I report, the
  lone members are counted with the standalones, which gives 87 against 25. In the modern window the
  standalone group is 12 films.
- **Effect on the client's number:** It reshapes the question. Nearly four in five candidates belong to a franchise, so this analysis tells Kwame which of *these* titles to buy and cannot tell him that
  franchise films are more available in the market generally. It also means every standalone statistic
  rests on a group small enough to move noticeably if one film enters or leaves.
- **What I did about it:** I kept all three categories, put the threshold in the settings file so
  the alternative can be run rather than argued about, and report the comparison both ways. Moving
  the nine lone members changes the standalone group by 56%, so the choice is published as a
  sensitivity row rather than hidden in a default.
- **Residual risk:** If those nine lone members really are films Kwame could buy individually, I am
  understating the franchise group by 10%. Counted the other way, a 16-film group becomes 25 and its
  typical figure is pulled by films whose performance may owe everything to a franchise this list does
  not contain. The second error is worse, which is why the default keeps them visible.

---

### F-05: Pre- and post-2000 money are not the same unit — Severity: High

- **What it is:** Budgets and box office are in the money of the year each film was released, and
  nothing adjusts them. Worse, an old film's takings keep accruing while its budget stays fixed:
  *Star Wars* was re-released in 1978, 1981 and 1997, so its revenue includes money earned decades
  after the 1977 cost it is being divided by.
- **How I detected it:** I compared the two eras side by side. Median budget is 5.0 times higher
  after 2000 while median revenue is only 2.3 times higher, which makes the typical return appear to
  halve across the boundary — 9.54 before 2000 against 4.92 after.
- **Scale:** 41 films before 2000, 71 after. Twenty of the 41 are franchise entries from Star Wars,
  Indiana Jones and The Godfather, so the distortion does not fall evenly between the two groups.
- **Effect on the client's number:** Pooling the eras would raise the apparent return of the whole
  catalogue and would specifically flatter the franchise side. It would also support a confident
  sentence — "the cheapest films to license return the most" — that is largely an artefact of
  measuring 1970s costs against 2020s receipts.
- **What I did about it:** I report each window separately and never compare a level across the
  boundary, and I use ranked measures rather than dollar amounts. I did not adjust for inflation:
  it needs data the brief does not supply, it would add a dependency to a pipeline that has to run
  from a clean clone, and deflating a lifetime revenue figure by its release-year index is still
  wrong, because the revenue was not all earned in that year.
- **Residual risk:** If the effect is weaker than I argue, nothing is lost, because both windows are
  reported either way and the reader is told why comparing them is unsafe. The effect grows as the
  back catalogue lengthens, so next year's list will make this worse rather than better.

---

### F-06: Every exceptional return on the list is an old film — Severity: High

- **What it is:** Eight films returned more than 20 times their budget, the highest being *Star
  Wars* at 70.5 times. All eight were released between 1966 and 1994. Not one modern film comes
  close.
- **How I detected it:** I flagged every unusual value with a verdict and a reason instead of
  filtering by a threshold, then looked at what the flagged rows had in common. All eight were
  classified as real extremes rather than errors.
- **Scale:** Eight of the 41 pre-2000 films, which is 20% of that era, and none of the 71 modern
  films.
- **Effect on the client's number:** This is why routine data cleaning would have been a mistake
  here. Winsorising or dropping outliers would have deleted a fifth of the pre-2000 evidence and
  nothing from the modern window. That is not hygiene. It makes the older era look worse while
  looking like standard practice, in exactly the window Finance is already sceptical about. It would
  also have removed the most relevant rows on the list: a 70-times return on a cheap 1977 film is
  the back-catalogue case, not noise.
- **What I did about it:** I kept every value, flagged each with a sentence saying why it is
  believable, and used medians, which resist extremes without removing them. I also forced all
  eight into the live spot-check by name rather than trusting them, because a check that samples the
  risky rows is not a check.
- **Residual risk:** If one of the eight is a bad figure, it inflates the pre-2000 picture. The
  spot-check re-fetched all eight and every money field matched the source. That tests my reading of
  the source rather than the source's own accuracy, which I cannot test from here.

---

### F-07: The franchise advantage on consistency does not survive into the modern window — Severity: Medium

- **What it is:** Across the whole catalogue, franchise films are not just better but far more
  predictable. Among films from 2000 onward that advantage disappears.
- **How I detected it:** I checked whether the answer flips between the two windows on every
  measure rather than only on the typical return. Had I checked the median alone I would have
  reported no flip and missed this.
- **Scale:** The spread of returns is 4.39 for franchise against 11.71 for standalones across all years.
  After 2000 it is 2.47 against 2.297 — a margin of 0.17, on 12 standalone films.
- **Effect on the client's number:** The recommendation holds on the typical return, the weaker end
  and the hit rate in both windows. Only consistency flips. So if anyone in the room argues that
  recent franchise films are the steadier bet, that specific claim is not supported.
- **What I did about it:** I report the flip with its group size beside it, and word it as "the
  advantage disappears" rather than "standalone titles are now safer". On 12 films and a margin of
  0.17, the second sentence would be the stronger claim and the wrong one.
- **Residual risk:** Four measures mean four chances to see a flip that is really noise, and this is
  probably one of them. Reporting the margin and the count is what lets a reader judge that for
  themselves.

---

### F-08: The position effect belongs to old franchises, and reverses in new ones — Severity: Medium

- **What it is:** Half of Kwame's team believes StreamVault overpays for the weak middle films of a
  franchise. Pooled across all years the data appears to agree, and the decline looks steep. Split
  the franchises by the era they *began* in and the effect reverses: old franchises decline hard,
  franchises that started this century do not decline at all.
- **How I detected it:** I noticed the opening films on this list are much older than the closing
  ones — first entries have a median release year of 2000 and half are pre-2000, while last entries
  median 2008.5 and only 14% are pre-2000 — and old films look more profitable for the reasons in
  F-05. So I read position inside an era instead of pooling, which turned out to be three different
  questions rather than one (below).
- **Scale:** 22 collections, 85 films pooled. Split by the era the franchise began in, the list
  divides almost exactly in half: 11 franchises born pre-2000, 11 born since.

  | | opener | middle | final | first → last |
  |---|---|---|---|---|
  | Pooled, all years | 7.76 | 5.41 | 4.44 | **−43%** |
  | Franchises born pre-2000 | 13.37 | 5.41 | 3.97 | **−70%** |
  | Franchises born 2000 or later | 5.30 | 5.39 | 6.08 | **+15%** |

  And taking each franchise against *itself*, which no change in the mix of franchises can move:
  of the 11 old franchises, **every single one** declines (median final entry 0.24× its own
  opener); of the 11 modern ones, 4 decline and the median final entry returns **1.27×** its own
  opener.
- **Effect on the client's number:** The team's belief is not supported for anything they would
  actually be buying. The decline is real but it belongs to franchises that began in the 1980s and
  1990s, whose openers have had twenty years of re-release, licensing and catalogue income against
  a fixed 1985 budget (F-05). Among franchises that began this century, later entries return
  **more** than their openers. So position in a franchise is **not** a discount argument for recent
  titles, and anyone using it as one is reading the age of the films. The middles are not the weak
  ones either.
- **What I did about it:** The pipeline computes and publishes all of it —
  `kpi_position_in_franchise.csv` (pooled), `kpi_position_in_franchise_modern.csv` (franchises born
  in the window) and `kpi_position_paired.csv` (each franchise against itself) — and the memo reads
  the within-era table and reports the sign it finds rather than a sign I assumed. Reporting the
  pooled figures alone would have handed the team a negotiating argument that does not apply to
  their candidates.
- **Residual risk:** 11 franchises on each side is thin, which is why the finding is stated as a
  direction with the paired check behind it rather than as a figure to negotiate with. The window
  keeps or drops a franchise **whole**, on the year of its opener; a franchise that began in 1977
  is therefore out of the modern window entirely, however recent its sequels. That costs sample and
  it is the price of having every cell hold the same franchises.
- **One honest footnote, because the figure moves with the definition.** "Position inside one era"
  can be read three ways, and they disagree:

  | Reading | first → last | Why I did not use it |
  |---|---|---|
  | Filter the films to 2000+, then rank | −7% | A franchise straddling 2000 is re-ranked, so its third film is counted as an opener |
  | Rank, then filter the films to 2000+ | +14% | Positions stay true, but the opener cell holds 11 franchises and the final cell 19 — different franchises, so part of the gap is a gap between sets |
  | **Keep franchises born 2000+, whole** | **−15%** | **Used.** Positions are true *and* every cell holds the same 11 franchises |

  Only the third compares like with like, and the paired check agrees with it. The middle reading
  is the one that produces the "about a seventh less" figure this finding carried for two drafts
  (see the note below), which is why the definition is written down here and not left to whoever
  re-runs this next quarter.
- **Corrected 2026-11-20.** For two drafts this finding said the decline shrank from 43% to about
  14% and that the middles held up while final entries slipped — a figure worked out by hand. The
  pipeline now computes it (S-07). The hand arithmetic was sound; the *definition* behind it was
  the middle reading in the table above, the one that compares different franchises in each cell.
  Under the reading that holds the franchises fixed the effect does not shrink, it reverses. The
  direction of the original decision — never read position without holding age still — was right
  and is what made the error findable.

---

### F-09: One IMDb identifier in a column of TMDb ids, and it was already on the list — Severity: Medium

- **What it is:** Row 95 of the candidate list holds `tt0468569`, which is an identifier from a
  different catalogue. Resolved, it turns out to be *The Dark Knight* — which already appears on the
  list twice, at rows 2 and 91.
- **How I detected it:** I read the file as text and checked every value against the shape of a
  TMDb id before parsing any of them. One row did not match. I then looked it up live rather than
  guessing.
- **Scale:** One row of 127. But the film it points to is a franchise entry, and it was already listed
  twice.
- **Effect on the client's number:** This is the one place in the data where the obvious fix and the
  correct fix are different. Recovering the row — which is what you would do if you only noticed
  that it was recoverable — would have put **three copies of one film** into every figure. All three
  would have landed on the franchise side of the central comparison, inflating the franchise median return, the franchise hit rate, and any talent figure touching Nolan or Bale.
- **What I did about it:** I wrote the resolution as a procedure rather than a one-off fix, because
  next quarter's list comes from the same three desks. It handles all three outcomes: no match, a
  match already on the list, or a match that is genuinely new. This row took the middle path and is
  recorded as a duplicate in a second identifier system. A genuinely new film would have been
  fetched and forced into the spot-check, because its provenance is unlike every other row.
- **Residual risk:** If the identification were wrong, one title would be missing from a pool of
  112, a 0.9% reduction. It is not wrong: the live response is cached and names the film and its
  release date. That is much the smaller error of the two available.

---

### F-10: Five ids have no film behind them, and they are not a random five — Severity: Medium

- **What it is:** Five of the 117 ids I tried returned "not found". They are `8471293`, `9412887`,
  `8471294`, `9412888` and `7733901`, at rows 18, 35, 73, 93 and 99.
- **How I detected it:** I recorded the response for every id instead of letting a failure stop the
  run, then asked what the five had in common.
- **Scale:** Five of 117, so the analysis runs on 112 films instead of 117. The pattern is the
  interesting part: every id that worked is **301,528 or below**, and every dead id is **7,733,901
  or above**. There is no overlap at all, a gap of twenty-five fold. Two pairs are consecutive.
- **Effect on the client's number:** TMDb issues ids in order, so an id in the 7-to-9 million range
  belongs to a catalogue entry created far more recently than any genuine back-catalogue film's
  entry would have been. The consecutive pairs suggest entries created one after another and later
  removed. On that evidence these five were probably never back-catalogue films, which makes losing
  them **less** damaging to the comparison than losing five random titles would be.
- **What I did about it:** I record each one as permanently unavailable with its reason, cache the
  response so reruns do not ask again, and deliberately do not retry: a missing film is an answer,
  and retrying it five times is both slower and rude to a service other people share. I report the
  id-range pattern rather than just the count.
- **Residual risk:** Unrecoverable either way. A deleted entry leaves no title to search for and ids
  are never reissued, so these five will fail forever. The honest limit is that because nothing is
  known about what they *were*, I cannot test whether the loss falls unevenly on older films or on franchises. "Probably never back-catalogue films" is an inference from the id range, not a check.

---

### F-11: The source returns co-directors in a different order on different films — Severity: Medium

- **What it is:** Nine of the 112 films have more than one credited director, and the source lists
  them in no fixed order. *The Matrix* gives Lana then Lilly Wachowski; *The Matrix Revolutions*
  gives Lilly then Lana. The Russo brothers are the same across *Infinity War* and *Endgame*.
- **How I detected it:** I compared the director lists of films I knew shared a directing team,
  rather than trusting that the first name in each list meant the same thing.
- **Scale:** Nine films of 112. Separately, 914 of 24,932 crew rows are the same person credited in
  two jobs on one film, which is why the crew table is one row per credit rather than per person.
- **Effect on the client's number:** Taking the first name in each list would credit the same
  partnership to different people on different films, which splits one body of work into several
  short ones. With a three-film minimum before I will call a name reliable, that is the difference
  between **11 directors** clearing the bar and **13**. The two that disappear are Lana and Lilly
  Wachowski: a three-film partnership split into one film each, so neither qualifies. They would not
  be reported as unreliable. They would not be reported at all.
- **What I did about it:** The film-level label is the partnership, sorted so it is identical on all
  three Matrix films, and every per-director figure is computed from a table holding one row per film
  per director, so a shared film counts for both of them. I also keep a count of directors per film
  so the nine can be found again.
- **Residual risk:** Crediting both directors with the full performance of a film they shared counts
  that record twice at the person level. That is the right error to make, because the alternative
  silently deletes people, and the question of whether talent is a reliable lever cannot be tested
  on a list that lost two of its most consistent names. Any recommendation naming a co-director has
  to say the films were shared.

---

## Looked wrong, is not wrong

| Apparent problem | Why it looks wrong | Why it is actually fine |
|---|---|---|
| Eight films return 20 to 70 times their budget | Returns that size look like a decimal point in the wrong place | They are real. All eight are cheap films from 1966 to 1994 whose takings accumulated over later re-releases, and all eight were re-checked against the live source. See F-06 |
| 914 crew rows repeat the same person on the same film | Looks like duplicated rows from a bad join | One person really did hold two jobs — a writer-director, a producer-director. The table is one row per credit, so this is expected. Any count of people has to deduplicate; any count of credits must not |
| Nine films have more than one director | Looks like the join multiplied rows | They were genuinely co-directed. The film count is unchanged; only the per-director view sees both names. See F-11 |
| 87 of 112 films belong to a franchise | A 78% split looks like a bug in the classification | The candidate list really is that lopsided. It was assembled from three sources that evidently favoured franchises. This is a fact about the list, not about the code, and it is why F-04 matters |
| `popularity` ranges from 0.46 to 85.7 | A 185-fold spread looks like a broken field | The field is real, but it is recomputed daily from recent activity and is heavily biased toward new films. I keep it as fetched and use it in nothing, because ranking a back catalogue by this week's attention would rank against the thing being valued |
| One film has five genres, another has one | Looks like missing data on the second | Both are correct. The source does not rank genres, so I never call one "primary" and never rank films by it |

## Could not verify

Ordered by how much it should reduce confidence.

1. **How these films behave on a streaming service.** I have cinema box office and public audience
   ratings. Those stand in for streaming value; they do not measure it. Every figure here describes
   how a film performed in cinemas, in some cases decades ago.
2. **What the five dead ids were.** Nothing is left to identify them, so I cannot test whether the
   loss falls unevenly on older films or on franchises. The id-range evidence makes a back-catalogue
   film unlikely, but unlikely is not checked.
3. **Whether the eight genuinely lost rows resemble the 112 kept.** There is no information left
   about what they were.
4. **Whether the source's own figures are correct.** The spot-check re-fetched 15 titles across four
   slices and every material field matched. That tests whether I read the source correctly, which is
   answerable. Whether the source is right about a 1977 budget is not answerable from here. The
   cache was also only hours old when I checked, so it is a weak test of whether values drift.
5. **What any of this costs.** There are no licensing prices in this data. The analysis can rank
   what to pursue and say what one set is worth relative to another. It cannot say what to pay, and
   anyone who produces a dollar figure from it is guessing.
6. **Kwame's own history.** Whether the trilogy he championed failed for the reasons assumed, and
   whether the five-film bundle StreamVault passed on was a miss, are out of scope by design. The
   method can score any bundle; proving the past is not this project's job.

---

Companion documents: [`../docs/self_audit.md`](../docs/self_audit.md) holds what I checked without
finding anything and the seven defects in my own work, two still open.
[`decision_notes.md`](decision_notes.md) holds the judgement calls behind the numbers above, and
[`../decisions/README.md`](../decisions/README.md) the decisions about how the pipeline is built.
