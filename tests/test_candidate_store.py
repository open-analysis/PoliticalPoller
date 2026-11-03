"""candidate_store.py: persistence, identity, corroboration, cycles, flags."""
import json

import pytest

import candidate_store as cs
from conftest import make_record as rec


def run(store_dir, records, **kw):
    return cs.upsert_candidates("mn", records, store_dir=store_dir, **kw)


def candidates(store):
    return [c for c in store.values() if isinstance(c, dict)]


# ---------------------------------------------------------------- hashing
class TestCandidateHash:
    def test_stable_and_16_hex_chars(self):
        h = cs.candidate_hash("Jane Doe", "Minnesota")
        assert h == cs.candidate_hash("Jane Doe", "Minnesota")
        assert len(h) == 16 and int(h, 16) >= 0

    def test_case_and_whitespace_insensitive(self):
        assert cs.candidate_hash("  JANE doe ", " minnesota") == cs.candidate_hash("Jane Doe", "Minnesota")

    def test_state_and_extra_change_the_hash(self):
        base = cs.candidate_hash("Jane Doe", "Minnesota")
        assert cs.candidate_hash("Jane Doe", "Iowa") != base
        assert cs.candidate_hash("Jane Doe", "Minnesota", extra="filer:1") != base
        assert (cs.candidate_hash("Jane Doe", "Minnesota", extra="filer:1")
                != cs.candidate_hash("Jane Doe", "Minnesota", extra="filer:2"))

    def test_none_values_do_not_crash(self):
        assert cs.candidate_hash(None, None)


# ---------------------------------------------------------------- helpers
class TestHelpers:
    @pytest.mark.parametrize("value,expected", [
        ("05/26/2026", 2026), ("2026-05-26", 2026), ("5/26/26", 2026),
        ("Filed May 26, 2026", 2026), ("", None), (None, None), ("garbage", None),
    ])
    def test_extract_cycle(self, value, expected):
        assert cs._extract_cycle({"file_date": value}) == expected

    @pytest.mark.parametrize("value,expected", [
        ("https://www.JaneDoe.com/about", "janedoe.com"),
        ("janedoe.com", "janedoe.com"),
        ("http://user@site.org:8080/x", "site.org"),
        ("N/A", ""), ("", ""), (None, ""),
    ])
    def test_website_domain(self, value, expected):
        assert cs._website_domain(value) == expected

    def test_norm_party(self):
        assert cs._norm_party("  Democratic   Farmer-Labor ") == "democratic farmer-labor"
        assert cs._norm_party(None) == ""

    def test_detect_collisions_needs_two_offices(self):
        same_office = [rec("A B", "Mayor"), rec("A B", "Mayor")]
        assert cs._detect_collisions(same_office) == {}
        two_offices = [rec("A B", "Mayor"), rec("A B", "Clerk"), rec("C D", "Mayor")]
        assert cs._detect_collisions(two_offices) == {"a b|minnesota": ["Clerk", "Mayor"]}

    def test_detect_collisions_ignores_nameless_rows(self):
        assert cs._detect_collisions([rec("", "Mayor"), rec("", "Clerk")]) == {}


# ---------------------------------------------------------------- persistence
class TestPersistence:
    def test_load_missing_store_is_empty(self, store_dir):
        assert cs.load_candidate_store("mn", store_dir) == {}

    def test_save_load_roundtrip_and_dir_creation(self, store_dir):
        cs.save_candidate_store("mn", {"x": {"candidate_name": "A"}}, store_dir)
        assert cs.load_candidate_store("mn", store_dir) == {"x": {"candidate_name": "A"}}

    def test_store_is_one_json_file_per_site(self, store_dir):
        run(store_dir, [rec("Jane Doe")])
        with open(cs._store_path("mn", store_dir), encoding="utf-8") as f:
            assert json.load(f)
        assert cs._store_path("mn", store_dir) != cs._store_path("ia", store_dir)

    def test_search_by_name_is_case_insensitive_substring(self, store_dir):
        store = run(store_dir, [rec("Jane Doe"), rec("John Roe")])["store"]
        assert [c["candidate_name"] for c in cs.search_by_name(store, "JANE")] == ["Jane Doe"]
        assert cs.search_by_name(store, "zzz") == []

    def test_search_ignores_reserved_keys(self, store_dir):
        store = run(store_dir, [rec("Jane Doe")])["store"]
        assert "_collisions" in store
        assert all(isinstance(c, dict) for c in cs.search_by_name(store, ""))


# ---------------------------------------------------------------- upsert basics
class TestUpsertBasics:
    def test_new_candidate(self, store_dir):
        r = run(store_dir, [rec("Jane Doe")])
        assert r["new_candidates"] == ["Jane Doe"] and r["unchanged"] == 0
        c = candidates(r["store"])[0]
        assert c["candidate_name"] == "Jane Doe"
        assert c["offices"]["Governor"]["party"] == "DFL"

    def test_rerun_is_unchanged_and_writes_nothing_new(self, store_dir):
        run(store_dir, [rec("Jane Doe")])
        r = run(store_dir, [rec("Jane Doe")])
        assert r["new_candidates"] == [] and r["updated_offices"] == [] and r["unchanged"] == 1

    def test_new_office_for_known_candidate(self, store_dir):
        run(store_dir, [rec("Jane Doe", "Governor", file_date="05/01/2026")])
        r = run(store_dir, [rec("Jane Doe", "Senator", file_date="05/02/2026")])
        assert r["new_offices"] == ["Jane Doe -- Senator"]
        assert set(candidates(r["store"])[0]["offices"]) == {"Governor", "Senator"}

    def test_changed_fields_are_refreshed_in_place(self, store_dir):
        run(store_dir, [rec("Jane Doe", website="https://old.com")])
        r = run(store_dir, [rec("Jane Doe", website="https://old.com/new")])
        assert r["updated_offices"] == ["Jane Doe -- Governor"]
        assert candidates(r["store"])[0]["offices"]["Governor"]["website"] == "https://old.com/new"

    def test_status_is_stored_and_refreshed(self, store_dir):
        row = rec("Jane Doe")
        run(store_dir, [{**row, "status": "Active"}])
        r = run(store_dir, [{**row, "status": "Withdrawn"}])
        assert r["updated_offices"] == ["Jane Doe -- Governor"]
        assert candidates(r["store"])[0]["offices"]["Governor"]["status"] == "Withdrawn"

    def test_nothing_is_deleted_when_a_row_disappears(self, store_dir):
        run(store_dir, [rec("Jane Doe"), rec("John Roe")])
        r = run(store_dir, [rec("Jane Doe")])
        assert {c["candidate_name"] for c in candidates(r["store"])} == {"Jane Doe", "John Roe"}

    def test_nameless_rows_are_skipped(self, store_dir):
        r = run(store_dir, [rec(""), rec(None)])
        assert candidates(r["store"]) == []

    def test_missing_office_becomes_unknown_office(self, store_dir):
        r = run(store_dir, [rec("Jane Doe", office=None)])
        assert "Unknown Office" in candidates(r["store"])[0]["offices"]

    def test_invalid_split_policy_rejected(self, store_dir):
        with pytest.raises(ValueError):
            run(store_dir, [rec("Jane Doe")], split_policy="sometimes")


# ---------------------------------------------------------------- same-scrape collisions
class TestSameScrapeCollisions:
    def test_two_offices_one_name_in_one_scrape_are_two_people(self, store_dir):
        r = run(store_dir, [rec("Pat Lee", "Governor"), rec("Pat Lee", "Senator")])
        assert len(candidates(r["store"])) == 2
        assert r["store"]["_collisions"] == ["pat lee|minnesota"]
        assert r["collisions"]

    def test_collision_is_remembered_on_later_runs(self, store_dir):
        run(store_dir, [rec("Pat Lee", "Governor"), rec("Pat Lee", "Senator")])
        r = run(store_dir, [rec("Pat Lee", "Governor")])  # only one of them shows up
        assert r["new_candidates"] == [] and r["unchanged"] == 1
        assert len(candidates(r["store"])) == 2


# ---------------------------------------------------------------- filer IDs
class TestFilerIds:
    def test_same_name_different_ids_never_merge(self, store_dir):
        r = run(store_dir, [rec("Pat Lee", "Governor", filer_id="A1"),
                            rec("Pat Lee", "Senator", filer_id="B2")])
        assert len(candidates(r["store"])) == 2
        assert r["review"] == []

    def test_same_id_survives_a_name_change(self, store_dir):
        run(store_dir, [rec("Pat Lee", filer_id="A1")])
        r = run(store_dir, [rec("Patricia Lee", filer_id="A1")])
        assert r["new_candidates"] == [] and len(candidates(r["store"])) == 1

    def test_id_is_attached_to_an_earlier_name_only_record(self, store_dir):
        run(store_dir, [rec("Sam Roe", "Auditor")])
        r = run(store_dir, [rec("Sam Roe", "Auditor", filer_id="Z9")])
        (c,) = candidates(r["store"])
        assert c["filer_id"] == "Z9" and r["new_candidates"] == []

    def test_id_not_attached_when_party_and_website_both_differ(self, store_dir):
        run(store_dir, [rec("Sam Roe", "Auditor", party="DFL", website="https://a.com", file_date="05/01/2024")])
        r = run(store_dir, [rec("Sam Roe", "Treasurer", party="GOP", website="https://b.org",
                                file_date="05/01/2026", filer_id="Z9")])
        assert len(candidates(r["store"])) == 2
        assert "split_conflict" in [f["kind"] for f in r["review"]]

    def test_ids_ignore_the_collision_list(self, store_dir):
        run(store_dir, [rec("Pat Lee", "Governor"), rec("Pat Lee", "Senator")])  # marks a collision
        r = run(store_dir, [rec("Pat Lee", "Governor", filer_id="A1")])
        assert any(c.get("filer_id") == "A1" for c in candidates(r["store"]))


# ---------------------------------------------------------------- corroboration
class TestCorroboration:
    BASE = dict(party="DFL", website="https://alkim.com", file_date="05/01/2022")

    def seed(self, store_dir):
        run(store_dir, [rec("Al Kim", "Governor", **self.BASE)])

    def test_no_conflict_merges_silently(self, store_dir):
        self.seed(store_dir)
        r = run(store_dir, [rec("Al Kim", "Senator", party="DFL", website="https://www.alkim.com/x",
                                file_date="05/01/2024")])
        assert len(candidates(r["store"])) == 1 and r["review"] == []

    def test_party_only_merges_with_flag(self, store_dir):
        self.seed(store_dir)
        r = run(store_dir, [rec("Al Kim", "Senator", party="GOP", website="https://alkim.com",
                                file_date="05/01/2024")])
        assert len(candidates(r["store"])) == 1
        assert [f["kind"] for f in r["review"]] == ["party_changed"]

    def test_website_only_merges_with_flag(self, store_dir):
        self.seed(store_dir)
        r = run(store_dir, [rec("Al Kim", "Senator", party="DFL", website="https://new.org",
                                file_date="05/01/2024")])
        assert len(candidates(r["store"])) == 1
        assert [f["kind"] for f in r["review"]] == ["website_changed"]

    def test_both_differ_splits_and_records_collision(self, store_dir):
        self.seed(store_dir)
        r = run(store_dir, [rec("Al Kim", "Senator", party="GOP", website="https://other.org",
                                file_date="05/01/2024")])
        assert len(candidates(r["store"])) == 2
        assert "al kim|minnesota" in r["store"]["_collisions"]
        assert r["collisions"] and "split_conflict" in [f["kind"] for f in r["review"]]

    def test_either_policy_splits_on_one_difference(self, store_dir):
        self.seed(store_dir)
        r = run(store_dir, [rec("Al Kim", "Senator", party="GOP", website="https://alkim.com",
                                file_date="05/01/2024")], split_policy="either")
        assert len(candidates(r["store"])) == 2

    def test_missing_values_are_not_conflicts(self, store_dir):
        self.seed(store_dir)
        r = run(store_dir, [rec("Al Kim", "Senator", party="", website="", file_date="05/01/2024")])
        assert len(candidates(r["store"])) == 1 and r["review"] == []

    def test_same_office_same_cycle_is_a_plain_update(self, store_dir):
        self.seed(store_dir)
        r = run(store_dir, [rec("Al Kim", "Governor", party="GOP", website="https://other.org",
                                file_date="05/09/2022")])
        assert len(candidates(r["store"])) == 1 and r["review"] == []
        assert r["updated_offices"] == ["Al Kim -- Governor"]

    def test_rerun_after_a_split_creates_no_duplicates(self, store_dir):
        self.seed(store_dir)
        rows = [rec("Al Kim", "Governor", **self.BASE),
                rec("Al Kim", "Senator", party="GOP", website="https://other.org", file_date="05/01/2024")]
        run(store_dir, rows[1:])
        r = run(store_dir, rows)
        assert r["new_candidates"] == [] and r["unchanged"] == 2
        assert len(candidates(r["store"])) == 2


# ---------------------------------------------------------------- cycles
class TestCycles:
    def test_cycle_stored_on_office_and_candidate(self, store_dir):
        (c,) = candidates(run(store_dir, [rec("Bo Tan", "Mayor", file_date="05/01/2022")])["store"])
        assert c["cycles"] == [2022] and c["offices"]["Mayor"]["cycle"] == 2022

    def test_no_readable_date_means_no_cycle(self, store_dir):
        (c,) = candidates(run(store_dir, [rec("Bo Tan", "Mayor", file_date="")])["store"])
        assert c["cycles"] == [] and c["offices"]["Mayor"]["cycle"] is None

    def test_same_office_later_cycle_keeps_history(self, store_dir):
        run(store_dir, [rec("Bo Tan", "Mayor", party="DFL", file_date="05/01/2022")])
        r = run(store_dir, [rec("Bo Tan", "Mayor", party="DFL", file_date="05/01/2024")])
        (c,) = candidates(r["store"])
        assert c["cycles"] == [2022, 2024]
        (old,) = c["offices"]["Mayor"]["history"]
        assert old["file_date"] == "05/01/2022"
        assert "cycle 2022 -> 2024" in r["updated_offices"][0]

    def test_gap_over_threshold_is_flagged(self, store_dir):
        run(store_dir, [rec("Bo Tan", "Mayor", file_date="05/01/2010")])
        r = run(store_dir, [rec("Bo Tan", "Mayor", file_date="05/01/2026")])
        assert [f["kind"] for f in r["review"]] == ["cycle_gap"]

    def test_gap_at_threshold_is_not_flagged(self, store_dir):
        run(store_dir, [rec("Bo Tan", "Mayor", file_date="05/01/2020")])
        r = run(store_dir, [rec("Bo Tan", "Mayor", file_date=f"05/01/{2020 + cs.CYCLE_GAP_WARN_YEARS}")])
        assert r["review"] == []

    def test_gap_not_flagged_when_a_filer_id_confirms_identity(self, store_dir):
        run(store_dir, [rec("Bo Tan", "Mayor", file_date="05/01/2010", filer_id="Q1")])
        r = run(store_dir, [rec("Bo Tan", "Mayor", file_date="05/01/2026", filer_id="Q1")])
        assert r["review"] == []

    def test_old_format_store_without_cycles_is_upgraded(self, store_dir):
        cid = cs.candidate_hash("Old Timer", "Minnesota")
        cs.save_candidate_store("mn", {cid: {
            "candidate_id": cid, "candidate_name": "Old Timer", "state": "Minnesota", "site": "mn",
            "offices": {"X": {"party": "DFL", "website": "https://o.com", "file_date": "01/01/2012",
                              "first_seen": "a", "last_seen": "a"}}}}, store_dir)
        r = run(store_dir, [rec("Old Timer", "Y", party="DFL", website="https://o.com", file_date="05/01/2026")])
        assert [f["kind"] for f in r["review"]] == ["cycle_gap"]
        assert candidates(r["store"])[0]["cycles"] == [2012, 2026]


# ---------------------------------------------------------------- review flags
class TestReviewFlags:
    def flagged(self, store_dir):
        run(store_dir, [rec("Bo Tan", "Mayor", file_date="05/01/2010")])
        return run(store_dir, [rec("Bo Tan", "Mayor", file_date="05/01/2026")])

    def test_flag_shape_and_count(self, store_dir):
        r = self.flagged(store_dir)
        (flag,) = r["review"]
        assert flag["status"] == "open" and flag["flag_id"] and flag["candidate_id"]
        assert r["open_review"] == 1

    def test_same_flag_is_not_raised_twice(self, store_dir):
        self.flagged(store_dir)
        r = run(store_dir, [rec("Bo Tan", "Mayor", file_date="05/01/2026")])
        assert r["review"] == [] and r["open_review"] == 1

    def test_list_and_dismiss(self, store_dir):
        self.flagged(store_dir)
        (flag,) = cs.list_review_flags("mn", store_dir=store_dir)
        assert cs.dismiss_review_flag("mn", flag["flag_id"], "checked", store_dir=store_dir) is True
        assert cs.list_review_flags("mn", store_dir=store_dir) == []
        (dismissed,) = cs.list_review_flags("mn", status="dismissed", store_dir=store_dir)
        assert dismissed["note"] == "checked"
        assert len(cs.list_review_flags("mn", status=None, store_dir=store_dir)) == 1

    def test_dismissed_flag_is_not_raised_again(self, store_dir):
        self.flagged(store_dir)
        (flag,) = cs.list_review_flags("mn", store_dir=store_dir)
        cs.dismiss_review_flag("mn", flag["flag_id"], store_dir=store_dir)
        r = run(store_dir, [rec("Bo Tan", "Mayor", file_date="05/01/2010"),
                            rec("Bo Tan", "Mayor", file_date="05/01/2026")])
        assert r["review"] == [] and r["open_review"] == 0

    def test_dismiss_unknown_flag_returns_false(self, store_dir):
        assert cs.dismiss_review_flag("mn", "nope", store_dir=store_dir) is False
