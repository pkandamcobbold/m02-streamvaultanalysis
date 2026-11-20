# Analysis method: every judgement call about what the numbers mean

The brief left most of these open and Kwame was unavailable, so each one was ours to decide. Each
record is in five parts: what we saw, what the real alternatives were, what we chose, what each
option does to the numbers, and what it costs him if the call was wrong.

**These are separate from [`../decisions/`](../decisions/README.md) on purpose.** Those records are about how the
system is built — the cache, the dtypes, the gate, the five stages. These are about what the
analysis means, and they are kept together because **they interlock**. M4 to M7 are four views of a
single problem: nominal money is not comparable across eras, so every statistic that touches money
has to answer for it. Read as four separate files you have to hold the argument in your head; read
in order it goes straight through.

Where a record names a finding (F-numbers), the evidence is in [`../reports/data_diagnosis.md`](../reports/data_diagnosis.md). Where
it names a question we could not settle ourselves (Q-numbers), it is in
[`questions.md`](questions.md).

| | Decision | Risk |
|---|---|---|
| **M1** | Three franchise categories, not two | **high** — it is the central split |
| **M2** | The crew table is one row per credit, not per person | medium |
| **M3** | A co-directed film counts for both directors | medium |
| **M4** | Money is compared within a window, never across one | **high** |
| **M5** | Extremes are flagged and classified, never clipped | **high** |
| **M6** | Medians and quartiles, with the mean shown beside them | **high** — it reverses the answer |
| **M7** | Position within a franchise is read inside one era | medium |
| **M8** | TMDb popularity is never a performance measure | medium |
| **M9** | The hit threshold stays at break-even; all three definitions reported | medium |
| **M10** | A relative measure is recomputed inside every window | medium |
| **M11** | The flip check tests every measure, not just the median | medium |
| **M12** | The shortlist labels what each pick actually is | medium |
| **M13** | Four stratified spot-check slices, not a random sample | medium |

If you read four of these, read **M1, M4, M5 and M6**: between them they decide which group wins,
and M6 is the one where the conventional choice would have reversed the recommendation.

---

## What we are comparing

### M1 — Three franchise categories, not two

### Context
96 of 112 films belong to a TMDb collection, but 9 of those are the *only* film of their collection
on the candidate list. A collection with one film on offer is not a bundle anyone can sell. So the
data has three groups, not the two the brief names: 87 franchise, 9 lone collection members, 16 true
standalones (F-04). This is the split the entire analysis rests on.

### Decision
Keep all three categories and decide the grouping at the KPI stage.
`franchise.min_members_on_list = 2` controls it, and the 9 lone members carry their own label so
they can be moved either way without recomputing anything.

### Alternatives considered
- **Franchise = belongs to any collection**, giving 96 against 16. The tempting option, and wrong:
  it counts a film as a bundle when there is no bundle to buy.
- **Franchise = at least 2 on the list, lone members folded into standalone**, giving 87 against 25.
  Defensible, and kept as the reported sensitivity rather than as the hidden default.

### Consequences
- Directly changes the central comparison's group sizes:

  | Definition | Franchise | Standalone |
  |---|---|---|
  | Any collection | 96 | 16 |
  | At least 2 on list, lone members to standalone | 87 | 25 |
  | Three groups *(chosen)* | 87 | 16, plus 9 reported separately |

- The headline is reported with lone members as standalone and a sensitivity row the other way,
  because moving 9 films out of a 16-film group changes it by 56%.
- If the 9 lone members really are franchise films Kwame could buy individually, excluding them
  understates the franchise group by 10% and overstates nothing. Treated as standalones instead, a
  16-film group becomes 25 and its median is pulled by films whose performance may owe everything
  to a franchise the list does not contain. The second error is worse, which is why the default
  keeps them visible.

### Revisit when
At 500 titles the lone-member group should shrink proportionally. If it does not, the list is being
assembled by picking single entries out of franchises, which is itself worth telling Kwame.

---

### M2 — The crew table is one row per credit, not per person

### Context
914 of 24,932 crew rows are the same person in more than one job on the same film: a
writer-director, a producer-director. And 9 of 112 films have more than one person credited as
Director.

### Decision
Keep one row per credit, and resolve the director question explicitly when collapsing to film
grain. Shaping the nested JSON changes shape and nothing else — no filtering, no cleaning, no
derived judgements — so every judgement lives in one place with a record. The one exception is the
franchise label (M1), which is named as derived.

### Alternatives considered
- **Deduplicate to one row per person per film** — loses the jobs, and makes any count of *credits*
  wrong while a count of *people* needs the deduplication. Both numbers have to be derivable from
  the same table.
- **Add a derived "primary director" column at this stage** — puts a judgement in the stage whose
  only job is shape.

### Consequences
- No effect on any number by construction. It determines what the join must handle: with 9
  multi-director films, a naive merge would silently pick whichever row comes first and produce a
  director attribution that is arbitrary but looks authoritative.
- A note is printed at every run, so the 914 figure is never a surprise.
- Any aggregation over this table has to state whether it is counting credits or people.

### Revisit when
A later question needs crew roles beyond Director. The grain already supports it; the note should
then name the roles in use.

---

### M3 — A co-directed film counts for both directors

### Context
9 of 112 films have more than one credited director, and **TMDb returns co-directors in no fixed
order**: `/movie/603` (*The Matrix*) lists Lana then Lilly Wachowski, `/movie/605` (*The Matrix
Revolutions*) lists Lilly then Lana. The same is true of the Russo brothers on *Infinity War* and
*Endgame*. Taking the first row therefore credits the same partnership to different people on
different films.

### Decision
Carry a sorted partnership label on the film table (`director_names`, identical on all three Matrix
films), plus `n_directors` to mark the 9, plus a long table at one row per film per director. Every
per-director statistic is computed from the long table, never from the label.

### Alternatives considered
- **Take the first row** — one director per film, whichever arrives first. Loses because the
  attribution is arbitrary and looks authoritative.
- **Take the first alphabetically as "the" director** — deterministic, and still discards a real
  co-director's filmography.

### Consequences
- **Measured, and it decides who exists in the talent analysis.** With
  `talent.min_films_for_reliable = 3`:

  | Collapse rule | Directors clearing 3 films |
  |---|---|
  | First row | **11** of 61 |
  | Both credited *(chosen)* | **13** of 66 |

- The two lost under the first-row rule are **Lana and Lilly Wachowski** — a 3-film partnership
  split into one film each, so neither clears the threshold and a consistent directing team
  disappears entirely. They would not be reported as unreliable; they would not be reported at all.
- The chosen rule credits each director with the full performance of a film they shared, so a
  partnership's record is counted twice at the person level. That is the right error to make: the
  alternative silently deletes people, and the claim that talent is a reliable lever cannot be
  tested against a list that lost two of its most consistent names.
- Any recommendation naming a co-director must say the films were shared, which `n_directors` makes
  possible. Per-film statistics are unaffected either way.

### Revisit when
A shortlist recommends a co-director without the shared-film caveat, or a partnership's doubled
weight changes which names clear the reliability threshold.

---

## The era problem, and the four decisions that follow from it

### M4 — Money is compared within a window, never across one

### Context
Budget and revenue are nominal. Median budget is 5.0 times higher post-2000, median revenue only
2.3 times higher, so median return appears to halve across the boundary: 9.54 pre-2000 against 4.92
after. And an old film's revenue is lifetime revenue: *Star Wars* was re-released in 1978, 1981 and
1997, so its numerator accumulates later, larger dollars against a 1977 denominator (F-05).

### Decision
Report each window separately and never compare a level across the boundary, alongside rank-based
measures — medians and quartile positions rather than dollar levels — which are scale-free. No
cross-window ratio appears anywhere in the memo.

### Alternatives considered
- **Pool all years and report one set of figures** — the 41 pre-2000 films would raise the apparent
  return of the whole catalog and, because 20 of those 41 are franchise entries from Star Wars,
  Indiana Jones and The Godfather, would specifically flatter the franchise side.
- **Adjust to constant dollars with an external CPI series** — needs data the brief does not
  provide, adds a dependency to a pipeline that must run from a clean clone, and **would not fix
  the problem**: deflating a lifetime revenue figure by the release-year CPI is still wrong, because
  the revenue was not all earned in the release year.

### Consequences
- This is why the two windows exist at all. Each window is internally comparable.
- If inflation and re-release effects are weaker than argued, nothing is lost: both windows are
  reported regardless, and the reader can compare them while being told why that comparison is
  unsafe.
- The opposite error produces a confident sentence — "the cheapest films to license return the
  most" — that is substantially an artefact of measuring 1970s costs against 2020s receipts.

### Revisit when
The candidate list spans more eras, which it will as the back catalog grows. The effect gets larger,
not smaller, at 500 titles.

---

### M5 — Extremes are flagged and classified, never clipped

### Context
Eight films have a return above 20 times budget, topping out at 70.5 times (*Star Wars*). **All
eight are pre-2000**, from 1966 to 1994 (F-06).

### Decision
Keep every value and flag it with a verdict and a sentence saying why. Four verdicts: `error`,
`real_extreme`, `unreliable`, `check`. All eight extremes are `real_extreme` and stay in every
metric.

### Alternatives considered
- **Winsorise at a percentile** — fires only on one era, so it is not hygiene.
- **Drop them as implausible** — deletes the most informative rows on the list.

### Consequences
- Either rejected option would delete **8 of 41 pre-2000 films (20%) and 0 of 71 modern films**. An
  outlier treatment that only ever fires on one era is a thumb on the scale of the comparison
  Finance is already sceptical about, and it would make their window look worse while looking like
  routine cleaning.
- It would also delete the back-catalog case itself: a 70 times return on a cheap 1977 film is the
  evidence, not noise.
- Instead, the reports use medians, which resist extremes without removing them, with counts beside
  every figure.
- If one of the eight is a bad figure, it inflates the pre-2000 picture. That is why all eight are
  forced into the live spot-check by name rather than trusted;
  `spotcheck.always_include_flagged` exists for this. The reverse error is larger and leaves no
  trace: a clipped value looks exactly like a value that was never there.

### Revisit when
The spot-check returns a material difference on any of the eight, or a future list has extremes in
both eras — at which point clipping stops being era-selective and the argument changes.

---

### M6 — Medians and quartiles, with the mean shown beside them

### Context
Computed both ways, the two statistics disagree about the recommendation. Mean return: standalone
**10.48**, franchise 7.94. Median return: franchise **5.53**, standalone 5.00. The eight
extreme-return films (F-06) are concentrated in the smaller group — 3 of 25 standalone films against
5 of 87 franchise films — so the standalone mean is pulled above the franchise mean while the typical
standalone film sits below the typical franchise film. This decision decides the answer.

### Decision
Report medians and quartiles, with the mean shown beside them so the disagreement is visible. Spread
is the interquartile range rather than the standard deviation, for the same reason: a standard
deviation inflated by a 70 times return says nothing about the typical gap between a good and a bad
film in the group.

### Alternatives considered
- **Report means**, the conventional default — would advise buying standalone hits on the strength of
  three films from 1975, 1966 and 1994.
- **Report means with the extremes winsorised** — rejected under M5: clipping would delete 20%
  of the pre-2000 films and none of the modern ones.

### Consequences
- **It reverses the recommendation.** Under means the memo would recommend standalone hits, on the
  strength of *Jaws*, *The Good, the Bad and the Ugly* and *Pulp Fiction* — returns no current
  acquisition can replicate. Under medians it recommends franchise bundles. Both figures are
  published in the KPI table, and the memo discloses the reversal rather than footnoting it.
- The median discards information about upside, and upside is part of an acquisition case: a buyer
  who wants one spectacular title rather than a reliable slate is served better by the mean. That
  reader is given the maximum and the full shortlist rather than being argued with.
- What the median protects against is the likelier error: taking a 1970s outlier as evidence about a
  2027 licensing deal.

### Revisit when
The gap between the two statistics closes, or a future list's extremes are spread evenly across the
groups — at which point the mean stops being the misleading one.

---

### M7 — Position within a franchise is read inside one era

### Context
Pooled across all years, return falls monotonically with position in a franchise: first 7.76, middle
5.41, last 4.44. But first entries have a median release year of 2000 and are 50% pre-2000, while
last entries median 2008.5 and are 14% pre-2000. Position is confounded with era, and era inflates
returns (M4). Half the team believes the *middle* entries are the weak ones.

### Decision
Report both the pooled and the within-era figures, name the confound, and quote the within-era
figures in the recommendation.

### Alternatives considered
- **Report the pooled figures** — supports the team's claim most strongly, and by three times the
  real margin. The most flattering and least useful outcome.
- **Report within-era figures only** — hides the size of the confound, which is itself a finding.

### Consequences
- The decline shrinks from **43% to 14%** from opener to final entry, so roughly two-thirds of the
  apparent effect was the era.
- The ranking changes: within one era, middle entries (5.05) sit *above* last entries (4.55), so the
  team's specific claim about middle entries is **not supported** even though the general direction
  is (F-08).
- The within-era groups are 11, 27 and 19 films, so the 14% is approximate and is given as such. The
  pre-2000 breakdown has only three "last" entries and is deliberately not reported as a finding.
- **Open item:** the pipeline's position artefact holds the pooled figures only. The within-era
  figures quoted in the memo were computed by hand from the cleaned table and are not yet produced
  by code, so they cannot be re-derived by a rerun. The artefact currently published is the version
  this record says not to quote.

### Revisit when
The open item above is closed by computing the within-era breakdown in the pipeline — at which point
the artefact and the memo quote the same numbers, and a rerun can falsify both.

---

## What counts as performance

### M8 — TMDb popularity is never a performance measure

### Context
`popularity` ranges from 0.46 to 85.70 on this list, and the top three are *Avengers: Endgame*
(2019), *Interstellar* (2014) and *The Dark Knight* (2008). It is a rolling engagement score
recomputed daily from recent page views, votes and watchlist adds.

### Decision
Exclude it from every metric and keep it in the tables as fetched.
`profile.use_popularity_as_performance = false` makes the choice visible rather than implied by its
absence — and setting it true refuses to load, because there is no code path for it (ADR-016).

### Alternatives considered
- **Use it as a demand proxy** — tempting, since licensing value is about future viewing. Loses on
  both counts below.
- **Use it only as a tie-breaker** — a tie-breaker that is recency-biased still decides which of two
  equal films is recommended, by the wrong criterion.

### Consequences
- Two reasons, and the second is the one that matters. It is **recency-biased**: a 2019 blockbuster
  outscores a 1966 classic by two orders of magnitude, so using it would rank against the back
  catalog this project exists to evaluate. And it is **not reproducible**: the cached value is a
  snapshot, so re-running the analysis next month from the same cache would give a different answer
  from a fresh fetch, and neither would be wrong. Every other field used here — budget, revenue,
  runtime, votes — is fixed once a film is released.
- Current audience interest is genuinely relevant to a licensing decision, and this discards it.
  Accepted, and stated in the memo as a limitation: the analysis measures historical performance,
  not present demand.

### Revisit when
A demand signal becomes available from a source whose values do not move under the analysis. That
is a different project, not a settings change.

---

### M9 — The hit threshold stays at break-even, and all three definitions are reported

### Context
`hit_roi_threshold` was set to 2.5 at the planning stage as a box-office break-even rule of thumb
and marked "to set after profiling". The profile shows **92% of the list clears it**, because the
list contains no film that lost money (F-01). The hit rate therefore barely discriminates between any
two groups.

| Return threshold | Share of the list counting as a hit |
|---|---|
| 2.0 | 95% |
| **2.5** | **92%** |
| 4.0 | 71% |
| 5.0 | 59% |
| 8.0 | 31% |

### Decision
Keep 2.5 for its external justification and report `above_median` and `top_quartile` alongside it,
showing where the three disagree. `report_all_hit_definitions = true` makes the fragility visible
instead of hiding it behind one number; `hit_definition` selects which one the reports lead with.

### Alternatives considered
- **Keep 2.5 and report the hit rate as the headline** — a metric that 92% of the list clears cannot
  carry a recommendation.
- **Raise the threshold until the metric separates the groups** — the trap. Choosing a threshold
  because it makes the numbers interesting is fitting the measure to the desired answer, and any
  figure chosen that way cannot survive the question "why 5.0?".

### Consequences
- The hit rate is demoted from a headline metric to one of three, and the memo leads with medians
  and spread instead.
- 2.5 keeps an answer to "why that number?" — roughly where a theatrical release breaks even after
  the exhibitor split and prints-and-advertising.
- `min_budget_for_roi` stays at 1,000,000 and is **inactive this quarter**: the smallest budget on
  the list is 1,200,000, so no film is excluded for return instability. It is kept as a guard for a
  future list containing a genuinely small film.
- If 2.5 is too low for this catalog, the hit rate is uninformative — which is exactly what is
  reported, so the reader is not misled.

### Revisit when
A future list contains films that lost money. The hit rate then starts discriminating, and the
threshold deserves re-examination against that distribution rather than against a rule of thumb.

---

### M10 — A relative measure is recomputed inside every window

### Context
Two of the three hit definitions are relative: `above_median` and `top_quartile` are defined against
a pool. The analysis reports two windows, all years and 2000 onward. Computing the flags once over
all 112 films and reusing them for the 71 modern films compares those films against a median set
partly by 1970s films, whose returns are inflated by inflation and re-release revenue (F-05).

### Decision
The function that adds hit flags takes a frame and computes within it, and the KPI stage calls it
again for each window.

### Alternatives considered
- **Compute once over everything and reuse** — cheaper, and reads as consistency. Loses because it
  answers a question nobody asked, and nothing in the output would reveal it.
- **Drop the relative definitions and keep only the absolute threshold** — the absolute threshold on
  its own is nearly useless here: 92% of the list clears it (M9).

### Consequences
- On this data, computing pool-wide instead of per window moves films across the "above median" line
  in the modern window, and in one direction only: modern films judged against a bar raised by older
  ones.
- A test pins the behaviour with a four-film case where the two methods disagree, because the bug
  produces no error and nothing in the output would show it.
- A reader who does want "above the all-years median" for a modern film can still compute it on the
  full table. The choice is explicit rather than inherited.

### Revisit when
A third window is added. The same rule applies, and the test should gain a case for it rather than
the code gaining a special case.

---

## How it is reported

### M11 — The flip check tests every measure, not just the median

### Context
The brief asks whether the recommendation changes in the post-2000 window. The planned check
compared one number per window. But the claim being tested — that franchise bundles are the *safer*
buy — is a claim about three measures: the floor, the spread and the hit rate. Checking only the
median would have reported "no flip" while one half of the claim had in fact reversed.

### Decision
Check each measure and report them separately. Four measures, each with its own direction
convention — and the interquartile range is explicitly marked "lower is better", because a tighter
group is the safer buy and reading it like a median inverts the answer.

### Alternatives considered
- **One check on the median** — would have missed the one flip that exists.
- **A single composite score combining them** — needs weights nobody has a basis to choose, and
  would hide exactly the disagreement worth reporting.

### Consequences
- It found one. Franchise films lead on median, floor and hit rate in both windows, and the
  **spread advantage flips** (F-07): interquartile range 4.39 against 11.71 across all years, 2.47
  against 2.297 after 2000.
- Four measures mean four chances to see a flip that is really noise, and this one is: a 0.17 margin
  on 12 films. Mitigated by reporting the margin and the count beside the flip rather than only the
  verdict, so the finding reads "the advantage disappears" and not "standalones are now safer".
- A flip on a headline measure moves to the memo's first line; a flip on spread gets its own
  paragraph.

### Revisit when
A flip appears on median, floor or hit rate. That is a different memo, and the rule that promotes it
to the first line is already in place.

---

### M12 — The shortlist labels what each pick actually is

### Context
Under the default grouping, lone collection members count as standalone (M1). The top five
"standalone" picks therefore include **Jaws** and **The Lion King**, both of which belong to a TMDb
collection whose other films are not on the candidate list.

### Decision
Keep them and carry `franchise_status` on every row of the shortlist, so the memo can name what each
pick is.

### Alternatives considered
- **Present them as standalones** — which the grouping says they are. Loses because calling *Jaws* a
  standalone without qualification is a sentence a board member could reasonably object to.
- **Drop them from the standalone shortlist** — chooses from 16 films rather than 25, making an
  already thin group (F-04) thinner and excluding two of its strongest candidates for a reason that
  has nothing to do with whether they can be bought.

### Consequences
- 2 of 5 selected standalones are lone collection members. The shortlist table carries the status
  and the memo names it: a single film Kwame can license on its own is exactly what the standalone
  side of the brief means.
- The three true standalones among the picks are *The Good, the Bad and the Ugly*, *Pulp Fiction*
  and *Schindler's List*.
- Costs one column.

### Revisit when
Lone collection members make up most of the standalone shortlist. At that point the grouping, not
the label, is what needs revisiting.

---

## How it is verified

### M13 — Four stratified spot-check slices, not a random sample

### Context
The brief asks for a spot-check sampled across four slices without naming them, and the budget is 3
films per slice. A simple random sample of 12 from 112 would, with high probability, contain **none**
of the eight extreme-return films that drive the analysis and none of the shortlisted titles the memo
names.

### Decision
Stratify: put the budget where an error would hurt, and keep one unbiased slice as a control. The
four slices are **shortlisted** (an error here is an error in the answer), **flagged_extreme** (the
eight films from F-06, *all* of them, because sampling the risky rows is not a check), **pre_2000**
(the distrusted window, where money is least comparable — M4), and **random_control** (without
it the check only looks where problems are expected). The sample is seeded, so a reviewer re-running
it sees the same films and can tell a fixed fault from a new draw.

### Alternatives considered
- **A random sample** — unbiased, and would mostly check films nobody cares about.
- **Check only the influential rows** — cannot detect a fault that is uniform across the list.

### Consequences
- 15 films rather than the 12 the plan estimated, because taking all eight flagged films costs more
  than sampling three. Coverage is 13% of the list and 100% of the rows the recommendation leans on.
- The checks stage hard-fails if the control slice is ever missing, unless the pool was small enough
  to be sampled entirely.
- A stratified sample cannot support a statement about the error rate of the list *as a whole*; the
  control slice is three films, which is too few to estimate anything. So the report claims fidelity
  on the rows checked and does not extrapolate a rate. The alternative is an unbiased estimate of a
  number nobody asked for, computed by not checking the films that matter.

### Revisit when
The list grows enough that 3 films per slice is a smaller share than it is now, or a material
difference is found in the control slice — which would mean the fault is not where the strata expect.

---

---

## A note on the "no row loops" requirement

Worth stating because it looks like an oversight otherwise. The requirement forbids looping over
rows to compute statistics. Every figure in the KPI tables comes from a named aggregation over a
group; no statistic is produced by iteration.

Acquisition does loop, because it is sequential I/O against a rate-limited service: a loop is the
correct shape, and vectorisation is meaningless when each step is a network round trip.

**Precisely what still iterates**, because an earlier version of this note claimed nothing past
acquisition did, and that was not accurate: classifying each cell of the id list; building the flag
table; classifying each film's money quality, which produces the eligibility and return columns that
feed every number; building the exclusions table; and filling the ledger's per-film columns. None
computes a statistic, and at 500 titles each is linear and sub-second — but the honest claim is "no
statistic is computed by iteration", not "nothing iterates".
