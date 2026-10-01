# -*- coding: utf-8 -*-

"""
Description: Persists scraped candidate records to a per-site JSON file,
    keyed by a stable per-candidate ID rather than by office, so the same
    person filing for a different office in a later cycle (or later in
    the same cycle) updates their existing record instead of creating a
    duplicate. Each candidate's record holds an "offices" dict so their
    full filing history -- every office they've ever run for on this
    site -- stays attached to one identity.

    Identity caveat, stated plainly: the source site gives us nothing
    stronger than a name to key on (no filer ID, no DOB, nothing). This
    module hashes normalized candidate_name + state to build an ID
    (candidate_hash()), which is enough to keep one real person's offices
    merged over time. It also runs a same-scrape collision check
    (_detect_collisions()): if two different offices show up under the
    same name+state in one scrape, that's treated as two different people
    (most filing sites don't let one person run for two offices in the
    same cycle), and that name+state is permanently flagged in the store
    so it's disambiguated by office on every later run too -- rather than
    silently merging a second same-named person into the first one's
    history. This catches the common case (two people with the same name
    both currently on the ballot) but not every case: two different
    people who happen to share a name and only ever appear one-at-a-time,
    cycle apart, are indistinguishable from one person switching offices,
    and would still merge. The honest fix for that remaining gap is to
    fold in a stronger field the moment the site ever exposes one (a
    filer/candidate ID, a district, a birth year) via candidate_hash()'s
    `extra` parameter.

    This is intentionally a plain JSON file, not a database: candidate
    filing data for one state is small (tens to low hundreds of rows),
    changes a handful of times a day at most even during filing season,
    and a JSON file is trivial to inspect, diff, or back up by hand.
    Swap in sqlite or a real DB here if a site's scale ever calls for it.
LLM: claude-sonnet-5
"""

import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone

DEFAULT_STORE_DIR = "candidate_data"


"""
Description: Builds the on-disk path for a site's candidate store file,
    creating store_dir if it doesn't exist yet.
Param[in] site:       Site key, e.g. "mn"
Param[in] store_dir:  Directory the per-site JSON files live in
Param[out] path:      Path to that site's candidates_<site>.json file
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def _store_path(site: str, store_dir: str = DEFAULT_STORE_DIR) -> str:
    os.makedirs(store_dir, exist_ok=True)
    return os.path.join(store_dir, f"candidates_{site}.json")


"""
Description: Builds a stable per-candidate ID from their normalized name
    (and state, since the same name is far more likely to collide
    state-to-state than within one). See the module docstring's identity
    caveat -- this cannot tell apart two different real people who share
    both a name and a state. Pass `extra` (e.g. a filer ID, district, or
    any other stronger field a site might expose) to fold it into the
    hash and get a correctly-distinct ID for that case instead.
Param[in] candidate_name:  Candidate's name as scraped
Param[in] state:           State the candidacy is in
Param[in] extra:           Optional additional disambiguating value
Param[out] candidate_id:   16-character hex ID, stable across calls for
    the same inputs
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def candidate_hash(candidate_name: str, state: str, extra: str = None) -> str:
    normalized = f"{(candidate_name or '').strip().lower()}|{(state or '').strip().lower()}"
    if extra:
        normalized += f"|{extra.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


"""
Description: Builds the normalized "name|state" key _detect_collisions()
    and upsert_candidates() use to group/track records by name+state,
    independent of office. Not a candidate's permanent ID -- see
    candidate_hash() for that.
Param[in] candidate_name:  Candidate's name as scraped
Param[in] state:           State the candidacy is in
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def _name_state_key(candidate_name: str, state: str) -> str:
    return f"{(candidate_name or '').strip().lower()}|{(state or '').strip().lower()}"


# Reserved store key holding every name+state pair ever confirmed to be a
# same-name collision (see _detect_collisions() / upsert_candidates()).
# Kept in the store itself, not just in-memory per call, so a collision
# detected once keeps that name+state disambiguated by office on every
# later run too -- even a run where only one of the two people shows up.
_COLLISIONS_KEY = "_collisions"


"""
Description: Finds every (name, state) pair that appears more than once
    in a single batch of fresh records under different offices. Since
    most filing sites don't allow one person to run for two different
    offices in the same cycle, two different offices under the same
    name+state in the SAME scrape is good evidence of two different
    people sharing a name -- not one person holding two jobs. This is a
    heuristic, not a certainty (an actual rule change or a clerical
    double-entry could also produce this shape), so callers should still
    treat a detected collision as something worth a human glancing at,
    not a silently-resolved non-issue.
Param[in] fresh_records:  List of candidate dicts, as returned by
    run_election_spider()
Param[out] collisions:    Dict of name_state_key -> sorted list of the
    distinct offices seen together for it in this batch
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def _detect_collisions(fresh_records: list) -> dict:
    offices_by_key = defaultdict(set)
    for record in fresh_records:
        name = record.get("candidate_name")
        if not name:
            continue
        key = _name_state_key(name, record.get("state"))
        offices_by_key[key].add(record.get("office") or "Unknown Office")

    return {key: sorted(offices) for key, offices in offices_by_key.items() if len(offices) > 1}


"""
Description: Loads the saved candidate store for a site, or an empty dict
    if nothing's been saved yet.
Param[in] site:       Site key, e.g. "mn"
Param[in] store_dir:  Directory the per-site JSON files live in
Param[out] store:     Dict keyed by candidate_id -> candidate record
    (candidate_id, candidate_name, site, state, first_seen, last_seen,
    offices: {office_name: {office_level, party, website, file_date,
    source_url, first_seen, last_seen}})
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def load_candidate_store(site: str, store_dir: str = DEFAULT_STORE_DIR) -> dict:
    path = _store_path(site, store_dir)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


"""
Description: Writes a candidate store dict back to disk for a site.
Param[in] site:       Site key, e.g. "mn"
Param[in] store:      Dict as returned by load_candidate_store() /
    upsert_candidates()
Param[in] store_dir:  Directory the per-site JSON files live in
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def save_candidate_store(site: str, store: dict, store_dir: str = DEFAULT_STORE_DIR) -> None:
    path = _store_path(site, store_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2, sort_keys=True)


"""
Description: Returns every saved candidate whose candidate_name contains
    `name` (case-insensitive substring match), across all offices they've
    ever been recorded for on that site.
Param[in] store:  A candidate store dict, as returned by
    load_candidate_store()
Param[in] name:   Name (or partial name) to search for
Param[out] matches: List of candidate record dicts
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def search_by_name(store: dict, name: str) -> list:
    needle = name.strip().lower()
    return [
        c for c in store.values()
        if isinstance(c, dict) and needle in (c.get("candidate_name") or "").lower()
    ]


# Office-level fields a fresh scrape can update for an already-known
# office. Not candidate_name/state (the identity itself) or that office's
# first_seen (set once, the first time we see them running for it).
_UPDATABLE_OFFICE_FIELDS = ("office_level", "party", "website", "file_date", "source_url")


"""
Description: Merges a fresh scrape (as returned by run_election_spider())
    into a site's saved candidate store. Matches each record to a
    candidate by candidate_hash(), NOT by office, so:
      - a brand-new name -> a new candidate record is created
      - a known candidate running for an office they haven't run for
        before (this cycle or a later one) -> that office is added to
        their existing record, other offices they've held stay intact
      - a known candidate + a known office, with changed party/website/
        file_date/etc -> that office's fields are refreshed in place
      - a known candidate + a known office, nothing changed -> counted
        unchanged, nothing written
    Nothing is ever deleted just because this run didn't see it (see the
    module docstring). Persists the merged store back to disk before
    returning.
Param[in] site:          Site key, e.g. "mn"
Param[in] fresh_records:  List of candidate dicts, as returned by
    run_election_spider()
Param[in] store_dir:      Directory the per-site JSON files live in
Param[out] summary:       Dict with "new_candidates" (names seen for the
    first time), "new_offices" (f"{name} -- {office}" for a known
    candidate's new office), "updated_offices" (same label shape, for a
    known candidate+office with changed fields), "unchanged" (a count),
    "collisions" (human-readable notes for any name+state pair just
    detected running under multiple offices in this one scrape -- see
    _detect_collisions()), and "store" (the full merged store that was
    just saved)
Owner: @opnanalysis
LLM: claude-sonnet-5
"""
def upsert_candidates(
    site: str,
    fresh_records: list,
    store_dir: str = DEFAULT_STORE_DIR,
) -> dict:
    store = load_candidate_store(site, store_dir)
    now = datetime.now(timezone.utc).isoformat()

    known_collisions = set(store.get(_COLLISIONS_KEY, []))
    newly_detected = _detect_collisions(fresh_records)
    collision_labels = []
    for key, offices in newly_detected.items():
        if key not in known_collisions:
            name = key.split("|", 1)[0]
            collision_labels.append(f"{name}: multiple people filed as {offices} in one scrape")
    known_collisions |= set(newly_detected.keys())
    store[_COLLISIONS_KEY] = sorted(known_collisions)

    new_candidates, new_offices, updated_offices, unchanged = [], [], [], 0

    for record in fresh_records:
        name = record.get("candidate_name")
        if not name:
            continue  # not a real row -- nothing to key or save

        state = record.get("state")
        office = record.get("office") or "Unknown Office"
        name_state_key = _name_state_key(name, state)

        # A name+state pair ever caught in a same-scrape collision (this
        # run or a past one) is treated as ambiguous going forward: scope
        # its identity to the specific office rather than letting a
        # same-named-different-person's row silently merge into someone
        # else's history. This does mean a *genuine* later office change
        # for someone caught in a collision won't be recognized as the
        # same person -- there's no way to tell which of the two people
        # moved without a stronger identifying field from the site (see
        # the module docstring).
        if name_state_key in known_collisions:
            cid = candidate_hash(name, state, extra=office)
        else:
            cid = candidate_hash(name, state)

        candidate = store.get(cid)
        is_new_candidate = candidate is None
        if is_new_candidate:
            candidate = {
                "candidate_id": cid,
                "candidate_name": name,
                "site": site,
                "state": state,
                "first_seen": now,
                "last_seen": now,
                "offices": {},
            }
            store[cid] = candidate
            new_candidates.append(name)
        else:
            candidate["last_seen"] = now

        fresh_office_fields = {field: record.get(field) for field in _UPDATABLE_OFFICE_FIELDS}
        existing_office = candidate["offices"].get(office)
        label = f"{name} -- {office}"

        if existing_office is None:
            new_office_entry = dict(fresh_office_fields)
            new_office_entry["first_seen"] = now
            new_office_entry["last_seen"] = now
            candidate["offices"][office] = new_office_entry
            if not is_new_candidate:
                # A known candidate showing up under an office we hadn't
                # seen for them before -- exactly the "runs again for a
                # different office later" case this store is meant to
                # keep associated with the same person.
                new_offices.append(label)
            continue

        changed_fields = [
            field for field in _UPDATABLE_OFFICE_FIELDS
            if fresh_office_fields.get(field) != existing_office.get(field)
        ]
        existing_office["last_seen"] = now
        if changed_fields:
            for field in changed_fields:
                existing_office[field] = fresh_office_fields[field]
            updated_offices.append(label)
        else:
            unchanged += 1

    save_candidate_store(site, store, store_dir)

    return {
        "new_candidates": new_candidates,
        "new_offices": new_offices,
        "updated_offices": updated_offices,
        "unchanged": unchanged,
        "collisions": collision_labels,
        "store": store,
    }
