"""Stage 3 tests.

A grain mistake does not raise. It produces a number that looks reasonable —
a median over a table with one film counted twice, a revenue total inflated by
the length of a cast list — and nothing downstream can detect it. So most of
these tests assert a shape rather than a value, and the ones that assert a
value are checking that a shape held.

The payload fixtures mirror the real cache: TMDb nests credits under
`credits`, puts `belongs_to_collection` as an object or null, and reuses the
field names `id`, `name`, `popularity` and `adult` in the film, the cast and
the crew — which is the collision this stage exists to resolve.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from streamvault.flatten import (
    CAST_COLUMNS,
    CREW_COLUMNS,
    FILM_COLUMNS,
    add_franchise_flags,
    assert_grains,
    build_cast,
    build_crew,
    build_films,
    build_genres,
    load_payloads,
)


def film(
    tmdb_id: int = 550,
    title: str = "Fight Club",
    collection: dict | None = None,
    cast: list | None = None,
    crew: list | None = None,
    genres: list | None = None,
    **overrides,
) -> dict:
    """A payload shaped like TMDb's, including the awkward parts."""
    payload = {
        "id": tmdb_id,
        "imdb_id": f"tt{tmdb_id:07d}",
        "title": title,
        "original_title": title,
        "release_date": "1999-10-15",
        "status": "Released",
        "budget": 63_000_000,
        "revenue": 100_853_753,
        "runtime": 139,
        "vote_average": 8.4,
        "vote_count": 27_000,
        "popularity": 61.4,
        "adult": False,
        "video": False,
        "original_language": "en",
        "belongs_to_collection": collection,
        "genres": genres if genres is not None else [{"id": 18, "name": "Drama"}],
        "credits": {
            "cast": cast if cast is not None else [
                {"id": 819, "name": "Edward Norton", "character": "The Narrator",
                 "order": 0, "gender": 2, "known_for_department": "Acting",
                 "popularity": 20.1, "adult": False},
            ],
            "crew": crew if crew is not None else [
                {"id": 7467, "name": "David Fincher", "job": "Director",
                 "department": "Directing", "gender": 2, "popularity": 9.9,
                 "adult": False},
            ],
        },
    }
    payload.update(overrides)
    return payload


IRON_MAN = {"id": 131292, "name": "Iron Man Collection",
            "poster_path": "/x.jpg", "backdrop_path": "/y.jpg"}


# --------------------------------------------------------------------------
# films — one row per film
# --------------------------------------------------------------------------

def test_films_is_one_row_per_film():
    films = build_films([film(550), film(155), film(603)])
    assert len(films) == 3
    assert films["tmdb_id"].is_unique
    assert films["tmdb_id"].tolist() == [155, 550, 603]   # sorted, deterministic


def test_no_column_is_called_id_or_name():
    """The collision that makes a later merge invent id_x and id_y."""
    films = build_films([film(550, collection=IRON_MAN)])
    cast = build_cast([film(550)])
    crew = build_crew([film(550)])
    genres = build_genres([film(550)])

    for table in (films, cast, crew, genres):
        assert "id" not in table.columns
        assert "name" not in table.columns
        assert not any("." in column for column in table.columns)


def test_the_collection_is_flattened_to_two_plain_columns():
    films = build_films([film(1726, collection=IRON_MAN), film(550)])
    by_id = films.set_index("tmdb_id")

    assert by_id.loc[1726, "collection_id"] == 131292
    assert by_id.loc[1726, "collection_name"] == "Iron Man Collection"
    assert pd.isna(by_id.loc[550, "collection_id"])
    assert pd.isna(by_id.loc[550, "collection_name"])


def test_ids_and_money_stay_integers():
    """A film with no runtime must not give every film a decimal point."""
    films = build_films([film(550), film(155, runtime=None, budget=None)])

    assert str(films["tmdb_id"].dtype) == "Int64"
    assert str(films["budget"].dtype) == "Int64"
    assert str(films["runtime"].dtype) == "Int64"
    assert str(films["collection_id"].dtype) == "Int64"
    assert films.loc[films["tmdb_id"] == 550, "budget"].item() == 63_000_000


def test_a_field_tmdb_stops_sending_becomes_an_empty_column():
    """Not a KeyError three stages later."""
    payload = film(550)
    del payload["runtime"]
    films = build_films([payload])

    assert list(films.columns) == FILM_COLUMNS
    assert pd.isna(films["runtime"].item())


def test_no_payloads_gives_an_empty_table_not_an_empty_frame():
    films = build_films([])
    assert list(films.columns) == FILM_COLUMNS
    assert len(films) == 0
    assert films["budget"].sum() == 0      # would be a KeyError on a bare frame


# --------------------------------------------------------------------------
# cast and crew — one row per credit
# --------------------------------------------------------------------------

def test_cast_is_one_row_per_film_per_member():
    payload = film(550, cast=[
        {"id": 819, "name": "Edward Norton", "character": "Narrator", "order": 0},
        {"id": 287, "name": "Brad Pitt", "character": "Tyler Durden", "order": 1},
    ])
    cast = build_cast([payload, film(155, cast=[
        {"id": 3894, "name": "Christian Bale", "character": "Bruce Wayne", "order": 0},
    ])])

    assert len(cast) == 3
    assert list(cast.columns) == CAST_COLUMNS
    assert cast.loc[cast["person_id"] == 287, "billing_order"].item() == 1
    assert sorted(cast["tmdb_id"].unique()) == [155, 550]


def test_billing_order_zero_is_the_lead_and_survives_as_zero():
    """A falsy value that must not be confused with missing."""
    cast = build_cast([film(550)])
    assert cast["billing_order"].item() == 0
    assert cast["billing_order"].notna().all()


def test_crew_keeps_one_row_per_credit_not_per_person():
    """A writer-director is two credits. Collapsing here would lose a fact."""
    payload = film(550, crew=[
        {"id": 7467, "name": "David Fincher", "job": "Director", "department": "Directing"},
        {"id": 7467, "name": "David Fincher", "job": "Producer", "department": "Production"},
    ])
    crew = build_crew([payload])

    assert len(crew) == 2
    assert list(crew.columns) == CREW_COLUMNS
    assert len(crew.drop_duplicates(["tmdb_id", "person_id"])) == 1
    assert set(crew["job"]) == {"Director", "Producer"}


def test_a_film_with_no_cast_keeps_its_row_in_films():
    """The failure that silently shrinks the film count."""
    payloads = [film(550), film(155, cast=[], crew=[])]
    films, cast, crew = build_films(payloads), build_cast(payloads), build_crew(payloads)

    assert len(films) == 2
    assert set(cast["tmdb_id"]) == {550}
    assert 155 in set(films["tmdb_id"])


def test_a_missing_credits_block_does_not_crash_the_stage():
    """json_normalize with record_path raises here; this must not."""
    payload = film(155)
    del payload["credits"]
    cast = build_cast([film(550), payload])

    assert len(cast) == 1
    assert cast["tmdb_id"].item() == 550


def test_an_absent_cast_field_becomes_na_not_a_crash():
    cast = build_cast([film(550, cast=[{"id": 819, "name": "Edward Norton"}])])
    assert cast["person_id"].item() == 819
    assert pd.isna(cast["character"].item())
    assert pd.isna(cast["billing_order"].item())


# --------------------------------------------------------------------------
# genres
# --------------------------------------------------------------------------

def test_genres_is_one_row_per_film_per_genre():
    genres = build_genres([
        film(550, genres=[{"id": 18, "name": "Drama"}, {"id": 53, "name": "Thriller"}]),
        film(155, genres=[{"id": 28, "name": "Action"}]),
    ])
    assert len(genres) == 3
    assert str(genres["genre_id"].dtype) == "Int64"
    assert set(genres.loc[genres["tmdb_id"] == 550, "genre_name"]) == {"Drama", "Thriller"}


def test_a_film_with_no_genres_is_absent_from_genres_but_not_from_films():
    payloads = [film(550), film(155, genres=[])]
    assert len(build_genres(payloads)) == 1
    assert len(build_films(payloads)) == 2


# --------------------------------------------------------------------------
# grain assertions
# --------------------------------------------------------------------------

def test_a_duplicated_film_row_is_a_hard_failure():
    """It would inflate every median and total, undetectably."""
    films = build_films([film(550), film(550)])
    with pytest.raises(AssertionError, match="more than one row"):
        assert_grains(films, build_cast([]), build_crew([]), build_genres([]))


def test_a_child_row_for_an_unknown_film_is_a_hard_failure():
    films = build_films([film(550)])
    cast = build_cast([film(999)])
    with pytest.raises(AssertionError, match="references films not in films"):
        assert_grains(films, cast, build_crew([]), build_genres([]))


def test_a_film_count_that_disagrees_with_the_fetch_is_a_hard_failure():
    films = build_films([film(550), film(155)])
    with pytest.raises(AssertionError, match="for 3 successful fetches"):
        assert_grains(films, build_cast([]), build_crew([]), build_genres([]),
                      expected_films=3)


def test_a_collection_name_without_an_id_is_a_hard_failure():
    """The franchise split rests entirely on this field."""
    films = build_films([film(550)])
    films.loc[0, "collection_name"] = "Orphan Collection"
    with pytest.raises(AssertionError, match="collection name with no collection id"):
        assert_grains(films, build_cast([]), build_crew([]), build_genres([]))


def test_a_film_with_no_cast_is_reported_as_a_note_not_a_crash():
    payloads = [film(550), film(155, cast=[])]
    notes = assert_grains(
        build_films(payloads), build_cast(payloads), build_crew(payloads),
        build_genres(payloads),
    )
    assert any("no cast rows" in note and "155" in note for note in notes)


def test_a_person_in_two_jobs_is_reported_as_expected_not_wrong():
    payload = film(550, crew=[
        {"id": 7467, "name": "David Fincher", "job": "Director", "department": "Directing"},
        {"id": 7467, "name": "David Fincher", "job": "Producer", "department": "Production"},
    ])
    notes = assert_grains(
        build_films([payload]), build_cast([payload]), build_crew([payload]),
        build_genres([payload]),
    )
    assert any("more than one job" in note for note in notes)


def test_clean_tables_produce_no_notes():
    payloads = [film(550), film(155)]
    notes = assert_grains(
        build_films(payloads), build_cast(payloads), build_crew(payloads),
        build_genres(payloads), expected_films=2,
    )
    assert notes == []


# --------------------------------------------------------------------------
# the franchise split — three categories, because the data has three
# --------------------------------------------------------------------------

def test_a_collection_with_two_films_on_the_list_is_a_franchise():
    films = add_franchise_flags(
        build_films([film(1726, collection=IRON_MAN), film(10138, collection=IRON_MAN)]),
        min_members_on_list=2,
    )
    assert set(films["franchise_status"]) == {"franchise"}
    assert films["collection_members_on_list"].tolist() == [2, 2]


def test_a_lone_member_of_a_collection_is_neither():
    """Not a bundle anyone can buy; also not a standalone film."""
    films = add_franchise_flags(
        build_films([film(1726, collection=IRON_MAN), film(550)]),
        min_members_on_list=2,
    )
    by_id = films.set_index("tmdb_id")

    assert by_id.loc[1726, "franchise_status"] == "lone_collection_member"
    assert by_id.loc[550, "franchise_status"] == "standalone"
    assert pd.isna(by_id.loc[550, "collection_members_on_list"])


def test_the_threshold_is_a_setting_so_the_alternative_stays_runnable():
    films = build_films([film(1726, collection=IRON_MAN), film(550)])

    strict = add_franchise_flags(films, min_members_on_list=2)
    loose = add_franchise_flags(films, min_members_on_list=1)

    assert strict.set_index("tmdb_id").loc[1726, "franchise_status"] == "lone_collection_member"
    assert loose.set_index("tmdb_id").loc[1726, "franchise_status"] == "franchise"
    assert loose.set_index("tmdb_id").loc[550, "franchise_status"] == "standalone"


def test_every_film_gets_exactly_one_status():
    films = add_franchise_flags(
        build_films([
            film(1726, collection=IRON_MAN), film(10138, collection=IRON_MAN),
            film(155, collection={"id": 263, "name": "Batman Collection"}),
            film(550),
        ]),
        min_members_on_list=2,
    )
    assert films["franchise_status"].notna().all()
    assert int(films["franchise_status"].value_counts().sum()) == len(films)
    assert set(films["franchise_status"]) <= {
        "franchise", "lone_collection_member", "standalone",
    }


# --------------------------------------------------------------------------
# reading the cache
# --------------------------------------------------------------------------

def _envelope(tmp_path, tmdb_id, status=200, payload=None, requested=None):
    path = tmp_path / f"{tmdb_id}__details_credits.json"
    path.write_text(json.dumps({
        "requested_id": requested if requested is not None else tmdb_id,
        "id_namespace": "tmdb",
        "endpoint": "details_credits",
        "http_status": status,
        "fetched_at": "2026-11-19T00:00:00+00:00",
        "payload": payload,
    }), encoding="utf-8")
    return path


def test_a_404_envelope_is_skipped_not_read_as_a_film(tmp_path):
    _envelope(tmp_path, 550, payload=film(550))
    _envelope(tmp_path, 999, status=404, payload=None)

    payloads, notes = load_payloads(tmp_path)
    assert len(payloads) == 1
    assert payloads[0]["id"] == 550
    assert any("held no film" in note for note in notes)


def test_a_redirected_id_is_reported(tmp_path):
    """Two of our ids being the same film is a finding, not a detail."""
    _envelope(tmp_path, 550, payload=film(999, title="Merged Entry"), requested=550)
    payloads, notes = load_payloads(tmp_path)

    assert len(payloads) == 1
    assert any("merged or redirected" in note for note in notes)


def test_a_clean_cache_reads_with_no_notes(tmp_path):
    _envelope(tmp_path, 550, payload=film(550))
    _envelope(tmp_path, 155, payload=film(155))
    payloads, notes = load_payloads(tmp_path)

    assert len(payloads) == 2
    assert notes == []
