# Decision notes

> **Deliverable.** Every judgement call where the brief left something open: what I assumed, why,
> what it costs Kwame if I am wrong, and what survives when Adjoa reruns this next year against 500
> titles without me.

Kwame was unavailable before the board review, and the brief says so: *"Where the brief doesn't
settle something, decide it, and say what you decided."* So these were mine to make. Where a call
should have been his, the record says so, and [`../docs/questions.md`](../docs/questions.md) carries
the question I would have asked.

Each record has five parts: **what I saw**, **the options**, **what I chose**, **what it does to the
numbers**, and **if I am wrong** — plus what survives at 500 titles, because the brief asks that
separately.

## Ranked by risk

Risk here means how much the decision moves the recommendation, not how hard it was to make. The
test is the one the brief sets: *can I say what the recommendation looks like under the alternative
I rejected?* If I cannot, it is not a decision note — it is a record of how the system is built, and
those live in [`../decisions/`](../decisions/README.md).

| | Decision | What the alternative would have done |
|---|---|---|
| **M6** | Judge by the typical film, not the average | **Reverses the recommendation** — averages would have me advise cherry-picking standalone hits, on the strength of three films from 1975, 1966 and 1994 |
| **M1** | Three franchise groups, not two | Turns the central comparison from 87 against 25 into 96 against 16, by counting films as bundles when there is no bundle to buy |
| **M14** | State the recommendation on what survives resampling | Lets the memo claim a gap that no measure establishes once sequels stop counting as independent results |
| **M4** | Never compare money across the 2000 line | Pooling the eras flatters the franchise side specifically, because 20 of the 41 older films are franchise entries |
| **M5** | Flag the extremes, never trim them | Trimming deletes 8 of 41 older films and none of the 71 recent ones — hurting the window Finance already distrusts, while looking like routine cleaning |
| **M9** | Keep the break-even bar where it is | Moving it until the groups separate is fitting the measure to the answer I wanted |
| **M7** | Read position-in-franchise within one era | The pooled figures tell the team they are right, by three times the real margin |
| **M3** | A co-directed film counts for both directors | Deletes two of the most consistent directors from the talent analysis — not as unreliable, but absent |
| **M10** | Recompute "above average" inside each window | Judges recent films against a bar raised by 1970s films, with nothing in the output to show it |
| **M11** | Test every measure for a flip, not just one | Reports "no flip" while half the team's safety claim had in fact reversed |
| **M13** | Choose the spot-check sample, don't draw it at random | A random 12 of 112 would check none of the eight films the analysis leans on |
| **M12** | Say what each shortlist pick actually is | Calls *Jaws* a standalone with no qualification, which a board member could fairly object to |
| **M8** | Never use the popularity score to measure performance | Ranks a back catalogue by this week's attention, and makes the analysis irreproducible |
| **M2** | One row per credit, not per person | Makes either the count of credits or the count of people wrong, with no way to get both |

Four records in [`../decisions/`](../decisions/README.md) pass the same test and belong to this
deliverable too. They are written up there in full rather than repeated here:

| | Decision | What the alternative would have done |
|---|---|---|
| **ADR-005** | Resolve the foreign id, then exclude it as a duplicate | Puts **three copies of one film** into every figure, all on the franchise side of the comparison |
| **ADR-009** | A film leaves a metric, never the analysis | Gives every metric a different denominator, so the memo's "112 films" stops being true halfway down the page |
| **ADR-004** | Treat the brief's title count as a claim, not an assertion | Crashes Adjoa's run for being correct about a bigger list |
| **ADR-006** | A missing film is a permanent answer | Wastes calls retrying, and leaves the pattern in the dead ids unexamined |

**Two things about how this is written.** The records below are grouped by theme, not by that
ranking: M4 to M7 are four views of one problem, and in rank order you lose the thread of the
argument. And the detail is proportionate to the risk — the top four get the full treatment, the
rest get what they need. A record that changes nothing does not deserve the same space as one that
reverses the answer.

## What survives at 500 titles

The definitional calls — M1, M2, M3, M9, M12 — survive unchanged, because they are about what a
thing *is* rather than how much of it there is. The era calls, M4 to M7, matter **more**, because a
longer back catalogue spans more eras. M13's sampling needs re-tuning, since three films per slice
is a smaller share of 500 than of 112. And M9's bar deserves a fresh look the first quarter the
list contains a film that lost money, because today 92% of the list clears it.

---

## What we are comparing

### M1 — Three franchise groups, not two

**Risk: 2 of 14.** This is the split the whole analysis rests on.

**What I saw.** 96 of the 112 films belong to a collection. But 9 of those are the only film of
their collection on Kwame's list — and a collection with one film on offer is not a bundle anyone
can sell him. So the data has three groups where the brief names two: 87 franchise films, 9 lone
members, and 16 true standalones (F-04).

**The options.** Call anything in a collection a franchise, which gives 96 against 16. Or require
two films on the list and fold the 9 lone members in with the standalones, which gives 87 against
25. Or keep all three groups and decide later.

**What I chose.** The third. A setting controls the threshold, and the 9 lone members carry their
own label so they can be moved either way without recomputing anything.

**What it does to the numbers.** It decides the size of both groups:

| Definition | Franchise | Standalone |
|---|---|---|
| Anything in a collection | 96 | 16 |
| Two or more on the list, lone members counted as standalone | 87 | 25 |
| Three groups *(chosen)* | 87 | 16, plus 9 reported separately |

The headline counts the lone members as standalone and publishes the other way as a sensitivity
row, because moving 9 films out of a 16-film group changes it by more than half. The first option
is the tempting one and it is wrong: it would call a film a bundle when there is no bundle to buy.

**If I am wrong.** If those 9 really are films Kwame could buy individually, I am understating the
franchise group by 10% and overstating nothing. Counted the other way, a 16-film group becomes 25
and its typical figure gets pulled by films whose performance may owe everything to a franchise his
list does not contain. The second mistake is the worse one, which is why the default keeps them
visible.

**At 500 titles.** The lone-member group should shrink in proportion. If it does not, somebody is
assembling the list by picking single entries out of franchises — which is itself worth telling him.

---

### M2 — One row per credit, not per person

**Risk: 14 of 14.** Changes no number; decides whether two later numbers can both be right.

**What I saw.** 914 of 24,932 crew rows are the same person doing two jobs on one film — a
writer-director, a producer-director. And 9 of the 112 films have more than one credited director.

**The options.** Collapse to one row per person per film, which loses the jobs. Add a "primary
director" column while shaping the data. Or keep one row per credit and settle the director
question later, where the judgement can be recorded.

**What I chose.** One row per credit. Shaping the data changes its shape and nothing else, so every
judgement lives in one place with a record against it.

**What it does to the numbers.** Nothing directly. It is what makes two counts possible from one
table: a count of *credits* must not deduplicate, and a count of *people* must. Collapsing early
would have made one of them permanently wrong. A note at every run reports the 914, so the figure
is never a surprise.

**If I am wrong.** Any total taken from this table has to say which of the two it is counting. That
is a standing obligation on whoever writes the next aggregation, and nothing in the code enforces it.

**At 500 titles.** Unchanged. If a later question needs crew roles beyond Director, the grain
already supports it.

---

### M3 — A co-directed film counts for both directors

**Risk: 8 of 14.** It decides who exists in the talent analysis.

**What I saw.** The source returns co-directors in no fixed order. *The Matrix* lists Lana then
Lilly Wachowski; *The Matrix Revolutions* lists Lilly then Lana. The Russo brothers are the same
across *Infinity War* and *Endgame*. So taking the first name credits the same partnership to
different people on different films.

**The options.** Take the first name returned. Take the first alphabetically, which is at least
deterministic. Or credit both, and keep a separate table at one row per film per director.

**What I chose.** Credit both. The film-level label is the sorted partnership, identical on all
three Matrix films, and every per-person figure comes from the long table rather than the label.

**What it does to the numbers.** With a three-film minimum before I will call a name reliable:

| Collapse rule | Directors clearing three films |
|---|---|
| First name returned | **11** of 61 |
| Both credited *(chosen)* | **13** of 66 |

The two that disappear under the first rule are Lana and Lilly Wachowski — a three-film partnership
split into one film each, so neither qualifies. They would not be reported as unreliable. They would
not be reported at all.

**If I am wrong.** Crediting both counts a shared record twice at the person level. That is the
better mistake: the alternative silently deletes people, and the question of whether talent is a
reliable lever cannot be tested on a list that lost two of its most consistent names. Any
recommendation naming a co-director has to say the films were shared.

**At 500 titles.** More partnerships, same rule. Watch for a doubled record pushing a name over the
reliability threshold on its own.

---

## The era problem, and the four decisions that follow from it

### M4 — Never compare money across the 2000 line

**Risk: 4 of 14.**

**What I saw.** Budgets and takings are in the money of each film's own year, with nothing adjusting
them. Median budget is 5.0 times higher after 2000 while median takings are only 2.3 times higher,
so the typical return appears to halve across the boundary — 9.54 before, 4.92 after. And an old
film's takings are *lifetime* takings: *Star Wars* was re-released in 1978, 1981 and 1997, so later
and larger dollars pile up against a 1977 cost (F-05).

**The options.** Pool everything and report one set of figures. Adjust to constant dollars using an
external inflation series. Or report each window separately and never compare a level across them.

**What I chose.** Separate windows, and rank-based measures rather than dollar levels. No
cross-window ratio appears anywhere in the memo.

**What it does to the numbers.** This is why two windows exist at all. Pooled, the 41 older films
would lift the apparent return of the whole catalogue — and because 20 of those 41 are franchise
entries from Star Wars, Indiana Jones and The Godfather, it would flatter the franchise side
specifically. I rejected the inflation adjustment because it needs data the brief does not supply,
adds a dependency to a pipeline that must run from a clean clone, and **would not fix the problem
anyway**: deflating a lifetime figure by its release-year index is still wrong, because the money
was not all earned in that year.

**If I am wrong.** If the effect is weaker than I argue, nothing is lost — both windows are reported
either way, and the reader is told why comparing them is unsafe. The opposite mistake produces a
confident sentence ("the cheapest films to license return the most") that is largely an artefact of
measuring 1970s costs against 2020s receipts.

**At 500 titles.** Worse, not better. A longer back catalogue spans more eras.

---

### M5 — Flag the extremes, never trim them

**Risk: 5 of 14.**

**What I saw.** Eight films returned more than 20 times their budget, topping out at 70.5 times for
*Star Wars*. **All eight are from 1966 to 1994.** Not one recent film comes close (F-06).

**The options.** Trim them at a percentile. Drop them as implausible. Or keep every value and flag
it with a verdict and a reason.

**What I chose.** Keep and flag. Each flag carries one of four verdicts — error, real extreme,
unreliable, needs a look — and all eight came out as real extremes that stay in every figure.

**What it does to the numbers.** Either rejected option would have deleted **8 of the 41 older films
and none of the 71 recent ones.** An outlier rule that only ever fires on one era is not hygiene. It
would make the window Finance already distrusts look worse, while looking like standard practice.
And it would delete the back-catalogue case itself: a 70-times return on a cheap 1977 film is the
evidence, not noise. Instead the reports use typical figures, which resist extremes without removing
them, with counts beside everything.

**If I am wrong.** If one of the eight is a bad figure, it inflates the older picture. That is why
all eight are forced into the live spot-check by name instead of being trusted. The reverse mistake
is bigger and leaves no trace at all: a trimmed value looks exactly like a value that was never
there.

**At 500 titles.** If a future list has extremes in both eras, trimming stops being era-selective
and this argument changes. Re-check that before reusing it.

---

### M6 — Judge by the typical film, not the average

**Risk: 1 of 14.** This is the decision that decides the answer.

**What I saw.** The two statistics disagree about the recommendation. On averages, standalones
return 10.48 against 7.94 for franchises. On typical films, franchises return 5.53 against 5.00.
The eight extreme films are concentrated in the smaller group — 3 of 25 standalones against 5 of 87
franchise films — so the standalone average is dragged above the franchise average while the typical
standalone film sits below the typical franchise film.

**The options.** Report averages, which is the conventional default. Report averages with the
extremes trimmed. Or report typical figures and the spread, with the average shown beside them.

**What I chose.** Typical figures and the spread, with the average printed alongside so the
disagreement is visible rather than buried. Spread is the middle-half range rather than the standard
deviation, for the same reason: a standard deviation inflated by a 70-times return says nothing
about the gap between a good and a bad film in the group.

**What it does to the numbers.** **It reverses the recommendation.** On averages the memo would
advise cherry-picking standalone hits, and the case would rest on *Jaws*, *The Good, the Bad and the
Ugly* and *Pulp Fiction* — returns nothing available today can repeat. On typical figures it advises
franchise bundles. Both are published, and the memo discloses the reversal without being asked.
Trimming the extremes instead was rejected under M5.

**If I am wrong.** The typical figure throws away information about upside, and upside is part of an
acquisition case. A buyer who wants one spectacular title rather than a reliable slate is better
served by the average — so that reader gets the maximum and the full shortlist rather than an
argument. What this protects against is the likelier mistake: treating a 1970s outlier as evidence
about a 2027 licensing deal.

**At 500 titles.** Watch whether the two statistics still disagree. If a future list spreads its
extremes evenly across the groups, the average stops being the misleading one.

---

### M7 — Read position-in-franchise within one era

**Risk: 7 of 14.**

**What I saw.** Pooled across all years, returns fall steadily with position in a franchise: 7.76
for openers, 5.41 for middles, 4.44 for final entries. But openers here are much older — half are
pre-2000, against 14% of final entries — and older films look more profitable for the reasons in M4.
Half of Kwame's team believes the *middle* films are the weak ones.

**The options.** Report the pooled figures. Report only the within-era figures. Or report both and
name the confound.

**What I chose.** Both, with the within-era figures quoted in the recommendation.

**What it does to the numbers.** It reverses the effect, which is more than I expected when I made
the call. The window keeps or drops a franchise whole, on the year of its opener, so that every
cell holds the same franchises:

| | opener | middle | final | first → last |
|---|---|---|---|---|
| Pooled, all years | 7.76 | 5.41 | 4.44 | −43% |
| Franchises born pre-2000 | 13.37 | 5.41 | 3.97 | −70% |
| **Franchises born 2000 or later** | **5.30** | **5.39** | **6.08** | **+15%** |

The decline is real and it belongs entirely to the old franchises — all 11 of them decline, median
final entry 0.24× its own opener — because their openers have had twenty years of catalogue income
against a 1985 budget (M4). Among the 11 franchises that began this century, 4 decline and the
median final entry returns 1.27× its own opener. So the team's belief is not supported for the
titles they would be buying, and reporting the pooled figures alone would have handed them a
discount argument that does not apply.

**If I am wrong.** 11 franchises on each side is thin, so this is stated as a direction with the
paired within-franchise check behind it, not as a figure to negotiate with. The whole-franchise
window also costs sample: a franchise that began in 1977 is out of the modern window entirely,
however recent its sequels.

**At 500 titles.** More franchises on each side makes this more reliable, not less. The comparison
to re-run is the same one, and the definition has to travel with it: read position inside an era,
and keep each franchise whole when you do.

**This record was corrected on 2026-11-20.** It previously said the decline shrank from 43% to 14%,
on a figure worked out by hand. The hand arithmetic was right for one reading of "inside one era" —
rank the films, then keep the post-2000 ones — but that reading puts 11 franchises in the opener
cell and 19 in the final cell, so part of what it measures is the difference between those sets.
Holding the franchises fixed, the effect reverses. F-08 sets out all three readings and what each
gives, because the figure moves with the definition and the definition is the decision.

---

## What counts as performance

### M8 — Never use the popularity score to measure performance

**Risk: 13 of 14.**

**What I saw.** The source's popularity score runs from 0.46 to 85.70 on this list, and the top
three are *Avengers: Endgame*, *Interstellar* and *The Dark Knight*. It is a rolling engagement
score, recomputed daily from recent views, votes and watchlist adds.

**The options.** Use it as a demand signal, which is tempting because licensing value is about
future viewing. Use it only to break ties. Or keep it in the tables and use it in nothing.

**What I chose.** The last. A setting makes the choice visible rather than implied by absence, and
turning it on refuses to load, because there is deliberately no code path for it (ADR-016).

**What it does to the numbers.** Nothing, and that is the point. Two reasons, and the second
matters more. It is **biased toward recent films**: a 2019 blockbuster outscores a 1966 classic by
two orders of magnitude, so using it would rank against the very back catalogue this project exists
to value. And it is **not reproducible**: the cached value is a snapshot, so rerunning next month
from the same data would disagree with a fresh fetch and neither would be wrong. Every other field
here — budget, takings, runtime, votes — is fixed once a film is released.

**If I am wrong.** Current audience interest is genuinely relevant to a licensing decision, and I am
discarding it. The memo says so as a limitation: this measures historical performance, not present
demand.

**At 500 titles.** Unchanged. A real demand signal would need a source whose values do not move
under the analysis, and that is a different project.

---

### M9 — Keep the break-even bar where it is

**Risk: 6 of 14.**

**What I saw.** The bar was set at 2.5 times budget during planning, as a rough theatrical
break-even, and marked "set this properly after profiling". Profiling showed **92% of the list
clears it**, because nothing on the list ever lost money (F-01). So the measure barely separates the
two groups.

| Bar | Share of the list counting as a hit |
|---|---|
| 2.0 | 95% |
| **2.5** | **92%** |
| 4.0 | 71% |
| 5.0 | 59% |
| 8.0 | 31% |

**The options.** Keep 2.5 and lead with the hit rate anyway. Raise the bar until the groups
separate. Or keep 2.5 for its outside justification and report two relative definitions beside it.

**What I chose.** The last. Reporting all three makes the fragility visible instead of hiding it
behind one number.

**What it does to the numbers.** The hit rate drops from a headline measure to one of three, and the
memo leads with typical figures and spread instead. Raising the bar was the trap: choosing a
threshold because it makes the numbers interesting is fitting the measure to the answer, and no
figure chosen that way survives the question "why 5.0?". 2.5 keeps an answer to that question — it
is roughly where a cinema release breaks even after the exhibitor's share and marketing.

**If I am wrong.** If 2.5 is too low for this catalogue, the hit rate is uninformative — which is
exactly what gets reported, so nobody is misled. A related guard sits unused: the minimum budget for
a stable return ratio is set at 1,000,000 and the smallest budget on the list is 1,200,000, so it
excludes nothing this quarter. It is kept for a future list with a genuinely small film on it.

**At 500 titles.** The first quarter the list contains a film that lost money, the hit rate starts
discriminating and this bar deserves re-examining against that distribution rather than a rule of
thumb.

---

### M10 — Recompute "above average" inside each window

**Risk: 9 of 14.**

**What I saw.** Two of the three hit definitions are relative — above the middle, and in the top
quarter — so they are defined against a pool. The analysis reports two windows. Working them out
once over all 112 films and reusing them for the 71 recent ones compares those films against a bar
set partly by 1970s films, whose returns are inflated for the reasons in M4.

**The options.** Compute once and reuse, which is cheaper and reads as consistency. Drop the
relative definitions. Or recompute inside each window.

**What I chose.** Recompute. The function takes a table and works within it, and the KPI stage calls
it again per window.

**What it does to the numbers.** On this data it moves films across the "above average" line in the
recent window, and in one direction only: recent films judged against a bar raised by older ones. A
test pins this with a four-film case where the two methods disagree, because the bug produces no
error and nothing in the output would reveal it. Dropping the relative definitions was not an option
worth taking, because the absolute bar on its own is nearly useless here — 92% of the list clears it
(M9).

**If I am wrong.** The two methods answer different questions, and this one answers the question the
brief asks. A reader who does want "above the all-years average" for a recent film can still compute
it; the choice is explicit rather than inherited.

**At 500 titles.** If a third window is added, the same rule applies and the test should gain a case
rather than the code gaining an exception.

---

## How it is reported

### M11 — Test every measure for a flip, not just one

**Risk: 10 of 14.**

**What I saw.** The brief asks whether the recommendation changes in the post-2000 window. My
planned check compared one number per window. But the claim being tested — that franchise bundles
are the *safer* buy — is a claim about three things: the weaker end, the spread, and the hit rate.
Checking only the typical figure would have reported "no flip" while half the claim had in fact
reversed.

**The options.** One check on the typical figure. A single combined score. Or check each measure and
report them separately.

**What I chose.** Each measure separately, each with its own direction. The spread is explicitly
marked "lower is better", because a tighter group is the safer buy and reading it like the others
inverts the answer.

**What it does to the numbers.** It found one. Franchise films lead on the typical figure, the
weaker end and the hit rate in both windows — and the **spread advantage flips** (F-07): a
middle-half range of 4.39 against 11.71 across all years, 2.47 against 2.297 after 2000. A combined
score was rejected because it needs weights nobody has a basis to choose, and would hide exactly the
disagreement worth reporting.

**If I am wrong.** Four measures mean four chances to see a flip that is really noise, and this one
probably is: a 0.17 margin on 12 films. So the margin and the count are reported beside the flip,
and it is worded "the advantage disappears" rather than "standalones are now safer".

**At 500 titles.** If a flip ever appears on the typical figure, the weaker end or the hit rate, that
is a different memo — and the rule that promotes it to the first line is already in place.

---

### M12 — Say what each shortlist pick actually is

**Risk: 12 of 14.**

**What I saw.** Under the default grouping, lone collection members count as standalone (M1). So the
top five "standalone" picks include **Jaws** and **The Lion King** — both of which belong to a
collection whose other films are not on Kwame's list.

**The options.** Present them as standalones, which is what the grouping says. Drop them from the
standalone shortlist. Or keep them and label what each one is.

**What I chose.** Keep and label. Every shortlist row carries its franchise status, so the memo can
name it.

**What it does to the numbers.** 2 of the 5 selected standalones are lone members, and the memo says
so. They are legitimate picks — a single film Kwame can license on its own is exactly what the
standalone side of the brief means — but calling *Jaws* a standalone without qualification is a
sentence a board member could fairly object to. The three true standalones among the picks are *The
Good, the Bad and the Ugly*, *Pulp Fiction* and *Schindler's List*.

**If I am wrong.** Dropping them would have chosen from 16 films instead of 25, making an already
thin group (F-04) thinner and excluding two of its strongest candidates for a reason that has
nothing to do with whether they can be bought. Labelling costs one column.

**At 500 titles.** If lone members come to dominate the standalone shortlist, it is the grouping
that needs revisiting, not the label.

---

## How it is verified

### M13 — Choose the spot-check sample, don't draw it at random

**Risk: 11 of 14.**

**What I saw.** The brief asks for a live spot-check across four slices without naming them, with a
budget of three films each. A straight random draw of 12 from 112 would very likely contain **none**
of the eight extreme-return films the analysis leans on, and none of the titles the memo names.

**The options.** Draw at random, which is unbiased and would mostly check films nobody cares about.
Check only the influential rows, which cannot detect a fault spread evenly across the list. Or
stratify, and keep one unbiased slice as a control.

**What I chose.** Stratify into four slices: the shortlisted titles, because an error there is an
error in the answer; **all eight** extreme films rather than a sample of them, because a check that
samples the risky rows is not a check; the pre-2000 window, where money is least comparable; and a
random control, without which the check only looks where problems are expected. The draw is seeded,
so a reviewer re-running it sees the same films and can tell a fixed fault from a fresh draw.

**What it does to the numbers.** 15 films rather than the 12 planned, because taking all eight
flagged films costs more than sampling three. That is 13% of the list and 100% of the rows the
recommendation leans on. The checks stage refuses to run if the control slice is ever missing.

**If I am wrong.** A chosen sample cannot support a claim about the error rate of the list as a
whole, and the control slice is three films, too few to estimate anything from. So the report claims
fidelity on the rows it checked and does not extrapolate a rate. The alternative was an unbiased
estimate of a number nobody asked for, bought by not checking the films that matter.

**At 500 titles.** Three per slice is a smaller share of 500 than of 112, so the budget needs
revisiting — and a material difference turning up in the control slice would mean the fault is not
where these slices expect it.

---

## A note on the "no row loops" requirement

The brief forbids looping over rows to compute statistics. Every figure in the KPI tables comes from
a grouped aggregation; no statistic is produced by iteration.

Fetching does loop, because it is sequential calls to a rate-limited service: a loop is the right
shape there, and vectorising is meaningless when each step is a network round trip.

**What still iterates**, stated precisely because an earlier version of this note claimed nothing
past fetching did, and that was not true: classifying each cell of the id list; building the flag
table; classifying each film's money quality, which produces the eligibility and return columns that
feed every number; building the exclusions table; and filling the ledger's per-film columns. None of
them computes a statistic, and at 500 titles each is linear and finishes in well under a second. The
honest claim is "no statistic is computed by iteration" — not "nothing iterates".

---

### M14 — State the recommendation on what survives resampling

**Risk: 3 of 14.** It decides what the central comparison is allowed to claim.

**What I saw.** The headline is a typical return of 5.53 for 87 franchise films against 5.00 for 25
standalones. Reported on its own that reads as settled, and it is not: two small groups with wide
spreads cannot establish a gap of half a turn. The brief asks for a recommendation Kwame can defend
in a room, and the first question in that room is "is that difference real?".

**The options.** Report the point estimates and let the reader assume — which is what the first
draft did, and it survives review only if nobody asks. Run a significance test, which answers a
question nobody at the table is asking. Or resample, publish the interval beside every headline
measure, and say which measures hold.

**What I chose.** The third, with one addition that changes the answer: resample **whole
franchises** as well as individual films. The 87 franchise films come from 23 collections, and
sequels share a cast, a director, an audience and a marketing budget, so counting them as 87
independent results overstates the evidence. Intervals rather than p-values, because Kwame is
deciding where to put $14M: "the gap could plausibly be anywhere from −6.2 to +3.2" tells him what
he needs and "p = 0.19" does not. The seed is in `settings.toml`, so a reviewer who re-runs sees the
same intervals and can tell a real change from a new draw.

**What it does to the numbers.** It moves no point estimate and it cost the memo its strongest
sentence. Resampling films, only the share clearing break-even excludes zero (+0.006 to +0.33).
Resampling the 23 whole franchises, **nothing does** — that one crosses zero by a thousandth. So
the memo no longer says franchise films return more. It says they are the more likely bet on all
four measures, on 78% to 97% of draws, and that no one measure settles it alone. That is a smaller
argument than the first draft made and it is one I can defend (F-02).

**If I am wrong.** The failure mode here is the unusual one: this may be too conservative. A
cluster bootstrap on 23 collections is itself a small-sample procedure and its intervals are wide
partly for arithmetic reasons. With 60 franchises the same gap may well clear zero. What I will not
do is quote the per-film interval because it is the flattering one.

**At 500 titles.** This gets better and cheaper at once — more clusters tighten the interval, and
"does the gap survive?" may start answering yes. The step is vectorised and runs in half a second on
112 films, so it scales with the table rather than with the number of draws.
