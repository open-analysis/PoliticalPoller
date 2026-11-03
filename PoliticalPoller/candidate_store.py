# -*- coding: utf-8 -*-

"""
Description: Persists scraped candidate records to a per-site JSON file,
    keyed by a stable per-candidate ID rather than by office, so the same
    person filing for a different office in a later cycle (or later in
    the same cycle) updates their existing record instead of creating a
    duplicate. Each candidate's record holds an "offices" dict so their
    full filing history -- every office they've ever run for on this
    site -- stays attached to one identity.

    Identity, in order of strength:
      1. A real site-provided ID. If a record carries "filer_id" (see the
         optional filer_id_selector / filer_id_index parser settings), that
         ID IS the identity: it is folded into candidate_hash() via
         `extra`, a later record with the same ID always lands on the same
         candidate (even if the name's spelling changes), and two people
         who share a name but have different IDs are never merged.
      2. Otherwise, normalized candidate_name + state (candidate_hash()).
         Nothing stronger is available, so before attaching a new office or
         a new election cycle to an existing name-matched candidate,
         _corroborate() compares party and the website's domain. If both
         differ the record is split off as its own candidate (and the name
         is added to the collisions list); if only one differs the records
         are merged but a review flag is raised, since a party or campaign
         site change between cycles is common and legitimate. A long gap
         between cycles on a name-only match is flagged too.
      3. Same-scrape collision check (_detect_collisions()): two different
         offices under one name+state in one scrape are treated as two
         different people, and that name+state is permanently flagged so
         it is disambiguated by office on every later run.
    Every office entry also records its election "cycle" (the year of
    file_date, when one can be read), and flags are stored in the store
    under "_review" so a human can look them over (see
    list_review_flags() / dismiss_review_flag()). Flags never block a
    merge by themselves and nothing is ever deleted automatically.

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
import re
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

DEFAULT_STORE_DIR = "candidate_data"

# A name-only match whose new election cycle is more than this many years
# away from every cycle already on file is flagged for review.
CYCLE_GAP_WARN_YEARS = 6

# When a name-only match disagrees with the stored candidate on party and/or
# website domain: "both" splits only if BOTH disagree (a party switch or a
# new campaign site alone is common, so those only raise a flag); "either"
# splits if EITHER disagrees (stricter, more duplicates to merge by hand).
DEFAULT_SPLIT_POLICY = "both"


"""
Description: Builds the on-disk path for a site's candidate store file,
    creating store_dir if it doesn't exist yet.
Param[in] site:       Site key, e.g. "mn"
Param[in] store_dir:  Directory the per-site JSON files live in
Param[out] path:      Path to that site's candidates_<site>.json file
Owner: @open-analysis
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
Owner: @open-analysis
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
Owner: @open-analysis
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
Owner: @open-analysis
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
Owner: @open-analysis
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
Owner: @open-analysis
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
Owner: @open-analysis
LLM: claude-sonnet-5
"""
def search_by_name(store: dict, name: str) -> list:
    needle = name.strip().lower()
    return [
        c for c in store.values()
        if isinstance(c, dict) and needle in (c.get("candidate_name") or "").lower()
    ]


# Reserved store key holding review flags (see _add_review_flag()).
_REVIEW_KEY = "_review"

# Office-level fields a fresh scrape can update for an already-known
# office. Not candidate_name/state (the identity itself) or that office's
# first_seen (set once, the first time we see them running for it).
_UPDATABLE_OFFICE_FIELDS = ("office_level", "party", "website", "file_date", "source_url", "cycle", "status")


"""
Description: Trims a scraped value to a plain string ("" for None).
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def _clean(value) -> str:
    return "" if value is None else str(value).strip()


"""
Description: Normalizes a party label for comparison (case and whitespace
    insensitive).
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def _norm_party(party) -> str:
    return " ".join(_clean(party).lower().split())


"""
Description: Reduces a website value to a bare lowercase domain without
    "www." for comparison. Returns "" when the value does not look like a
    web address (the scraper falls back to cell text, which can be "N/A"
    or similar), so it is treated as "no value".
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def _website_domain(website) -> str:
    value = _clean(website).lower()
    if not value:
        return ""
    if "://" not in value:
        value = "http://" + value
    host = urlparse(value).netloc.split("@")[-1].split(":")[0]
    if "." not in host:
        return ""
    return host[4:] if host.startswith("www.") else host


_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_SHORT_DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-](\d{2})\b")


"""
Description: Works out the election cycle (a year) for a record from the
    year in its file_date ("2026-05-26", "5/26/2026", or "5/26/26").
    Returns None if no year can be read, in which case cycle-based checks
    are skipped for that record rather than guessed. Note this is the year
    the candidate FILED, so a site that opens filing the year before the
    election (e.g. Nov 2025 for 2026) reports the earlier year.
Param[in] record:  Any dict with an optional "file_date"
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def _extract_cycle(record: dict):
    file_date = _clean(record.get("file_date"))
    match = _YEAR_RE.search(file_date)
    if match:
        return int(match.group(0))
    match = _SHORT_DATE_RE.search(file_date)
    if match:
        return 2000 + int(match.group(1))
    return None


"""
Description: Returns the (office_name, entry) a candidate was most recently
    filed under: highest cycle first, then most recently seen.
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def _latest_office_entry(candidate: dict):
    offices = candidate.get("offices") or {}
    if not offices:
        return None, None
    name = max(
        offices,
        key=lambda o: (offices[o].get("cycle") or 0, offices[o].get("last_seen") or ""),
    )
    return name, offices[name]


"""
Description: Decides whether a fresh record that name-matches an existing
    candidate (no site ID to say for sure) should be merged into them, and
    which review flags to raise either way. Only runs when the record would
    attach a NEW office or a NEW cycle to the candidate; a same-office,
    same-cycle row is just the same filing being refreshed.
    Compares the fresh record to the candidate's most recent filing:
      - party differs (both non-empty, case-insensitive)
      - website domain differs (both non-empty, ignoring "www.")
    and splits per `split_policy` ("both" or "either"); anything short of a
    split that still differs becomes a "party_changed"/"website_changed"
    flag. Also raises "cycle_gap" if the new cycle is more than
    CYCLE_GAP_WARN_YEARS from every cycle already on file.
Param[in] candidate:     Existing candidate record
Param[in] record:        Fresh record
Param[in] office:        Fresh record's office
Param[in] cycle:         Fresh record's cycle, or None
Param[in] split_policy:  "both" or "either"
Param[out] result:       (should_split, [(kind, detail), ...])
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def _corroborate(candidate: dict, record: dict, office: str, cycle, split_policy: str):
    offices = candidate.get("offices") or {}
    existing_entry = offices.get(office)
    existing_cycle = (existing_entry or {}).get("cycle")
    if existing_entry is not None and (cycle is None or existing_cycle is None or cycle == existing_cycle):
        return False, []  # same filing being refreshed, not a new one

    flags = []
    _, latest = _latest_office_entry(candidate)
    name = candidate.get("candidate_name")
    party_conflict = site_conflict = False
    if latest:
        old_party, new_party = _norm_party(latest.get("party")), _norm_party(record.get("party"))
        old_site, new_site = _website_domain(latest.get("website")), _website_domain(record.get("website"))
        party_conflict = bool(old_party and new_party and old_party != new_party)
        site_conflict = bool(old_site and new_site and old_site != new_site)
        if party_conflict:
            flags.append(("party_changed", f"{name}: party {latest.get('party')!r} -> {record.get('party')!r} "
                                           f"(now {office}, cycle {cycle})"))
        if site_conflict:
            flags.append(("website_changed", f"{name}: website {old_site!r} -> {new_site!r} "
                                             f"(now {office}, cycle {cycle})"))

    should_split = (party_conflict and site_conflict) if split_policy == "both" else (party_conflict or site_conflict)

    known_cycles = candidate.get("cycles") or sorted(
        {c for c in ((e.get("cycle") or _extract_cycle(e)) for e in offices.values()) if c}
    )
    if cycle is not None and known_cycles and cycle not in known_cycles:
        gap = min(abs(cycle - c) for c in known_cycles)
        if gap > CYCLE_GAP_WARN_YEARS:
            flags.append(("cycle_gap", f"{name}: {gap}-year gap since cycle(s) {known_cycles}; "
                                       f"now {office}, cycle {cycle} -- same person?"))
    return should_split, flags


"""
Description: Records a human-review flag in the store under "_review",
    unless an identical one (same candidate, kind, and detail) is already
    there -- including a dismissed one, so a flag a person has dismissed
    does not come back on the next sync.
Param[out] added:  True if a new flag was recorded
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def _add_review_flag(store: dict, new_flags: list, cid: str, kind: str, detail: str, now: str) -> bool:
    flags = store.setdefault(_REVIEW_KEY, [])
    flag_id = hashlib.sha256(f"{cid}|{kind}|{detail}".encode("utf-8")).hexdigest()[:12]
    if any(f.get("flag_id") == flag_id for f in flags):
        return False
    flag = {"flag_id": flag_id, "candidate_id": cid, "kind": kind, "detail": detail,
            "status": "open", "flagged_at": now}
    flags.append(flag)
    new_flags.append(flag)
    return True


"""
Description: Returns the review flags saved for a site, newest last.
Param[in] site:       Site key, e.g. "mn"
Param[in] status:     "open" (default), "dismissed", or None for all
Param[in] store_dir:  Directory the per-site JSON files live in
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def list_review_flags(site: str, status: str = "open", store_dir: str = DEFAULT_STORE_DIR) -> list:
    flags = load_candidate_store(site, store_dir).get(_REVIEW_KEY, [])
    return [f for f in flags if status is None or f.get("status") == status]


"""
Description: Marks a review flag as dismissed (a person looked at it and
    decided it is fine, or fixed it by hand) so it stops being listed as
    open. The flag is kept, not deleted, so it is not raised again.
Param[in] site:       Site key, e.g. "mn"
Param[in] flag_id:    flag_id from list_review_flags()
Param[in] note:       Optional note on why
Param[in] store_dir:  Directory the per-site JSON files live in
Param[out] found:     True if a matching open flag was dismissed
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def dismiss_review_flag(site: str, flag_id: str, note: str = None, store_dir: str = DEFAULT_STORE_DIR) -> bool:
    store = load_candidate_store(site, store_dir)
    for flag in store.get(_REVIEW_KEY, []):
        if flag.get("flag_id") == flag_id and flag.get("status") == "open":
            flag["status"] = "dismissed"
            flag["dismissed_at"] = datetime.now(timezone.utc).isoformat()
            if note:
                flag["note"] = note
            save_candidate_store(site, store, store_dir)
            return True
    return False


"""
Description: Merges a fresh scrape (as returned by run_election_spider())
    into a site's saved candidate store, resolving each record to a
    candidate like this:
      1. record has "filer_id": the candidate already holding that ID, or
         (if none) a name-only record with no ID yet that passes
         _corroborate() (the ID is attached to it, keeping its history),
         or else a new candidate hashed with the ID as candidate_hash()'s
         `extra`. Same-name people with different IDs are never merged.
      2. no ID, and the name+state is in the collisions list: the
         candidate that already holds this office, else one scoped to this
         office via `extra`.
      3. no ID: the candidate hashed from name+state, after _corroborate()
         clears attaching a new office/cycle to them. If it says split, the
         record becomes its own office-scoped candidate and the name+state
         is added to the collisions list.
    Then, per office: a new office is added, an unchanged one is counted,
    a changed one is refreshed in place, and the same office filed in a
    later cycle first has its previous values pushed onto that entry's
    "history" list. Each office entry carries its "cycle"; the candidate
    carries a sorted "cycles" list. Nothing is deleted because one run
    did not see it. Persists the merged store before returning.
Param[in] site:           Site key, e.g. "mn"
Param[in] fresh_records:  List of candidate dicts, as returned by
    run_election_spider() (optionally with "filer_id")
Param[in] store_dir:      Directory the per-site JSON files live in
Param[in] split_policy:   "both" (default) or "either" -- see
    DEFAULT_SPLIT_POLICY
Param[out] summary:       Dict with "new_candidates", "new_offices",
    "updated_offices", "unchanged" (count), "collisions" (notes on name
    collisions, including splits made this run), "review" (the review
    flags newly raised this run), "open_review" (count of all open
    flags), and "store" (the full merged store that was saved)
Owner: @open-analysis
LLM: claude-sonnet-5.5
"""
def upsert_candidates(
    site: str,
    fresh_records: list,
    store_dir: str = DEFAULT_STORE_DIR,
    split_policy: str = DEFAULT_SPLIT_POLICY,
) -> dict:
    if split_policy not in ("both", "either"):
        raise ValueError("split_policy must be 'both' or 'either'")

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

    filer_index = {
        c["filer_id"]: cid for cid, c in store.items()
        if isinstance(c, dict) and c.get("filer_id")
    }
    new_flags = []
    new_candidates, new_offices, updated_offices, unchanged = [], [], [], 0

    for record in fresh_records:
        name = record.get("candidate_name")
        if not name:
            continue  # not a real row -- nothing to key or save

        state = record.get("state")
        office = record.get("office") or "Unknown Office"
        name_state_key = _name_state_key(name, state)
        filer_id = _clean(record.get("filer_id")) or None
        cycle = _extract_cycle(record)
        plain_cid = candidate_hash(name, state)
        pending_flags = []  # (kind, detail) -- recorded once cid is final

        if filer_id:
            cid = filer_index.get(filer_id)
            if cid is None:
                adoptable = store.get(plain_cid)
                if (isinstance(adoptable, dict) and not adoptable.get("filer_id")
                        and name_state_key not in known_collisions):
                    split, found = _corroborate(adoptable, record, office, cycle, split_policy)
                    pending_flags += found
                    if split:
                        pending_flags.append(("split_conflict",
                            f"{name}: new filer_id {filer_id} not attached to the existing name-only "
                            f"record (party and website both differ); kept separate"))
                        cid = candidate_hash(name, state, extra=f"filer:{filer_id}")
                    else:
                        cid = plain_cid  # adopt: attach the ID to their history
                else:
                    cid = candidate_hash(name, state, extra=f"filer:{filer_id}")
        elif name_state_key in known_collisions:
            holder = store.get(plain_cid)
            if isinstance(holder, dict) and office in holder.get("offices", {}):
                cid = plain_cid
            else:
                cid = candidate_hash(name, state, extra=office)
        else:
            cid = plain_cid
            existing = store.get(cid)
            if isinstance(existing, dict):
                split, found = _corroborate(existing, record, office, cycle, split_policy)
                pending_flags += found
                if split:
                    known_collisions.add(name_state_key)
                    cid = candidate_hash(name, state, extra=office)
                    collision_labels.append(
                        f"{name}: split into a separate record for {office} (cycle {cycle}) -- party and "
                        f"website both differ from their earlier filing")
                    pending_flags.append(("split_conflict",
                        f"{name}: {office} (cycle {cycle}) kept separate from their earlier record"))

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
                "cycles": [],
                "offices": {},
            }
            store[cid] = candidate
            new_candidates.append(name)
        else:
            candidate["last_seen"] = now

        if filer_id:
            candidate["filer_id"] = filer_id
            filer_index[filer_id] = cid

        # Backfill cycle data on records saved before cycles existed.
        for entry in candidate["offices"].values():
            entry.setdefault("cycle", _extract_cycle(entry))
        if not candidate.get("cycles"):
            candidate["cycles"] = sorted({e["cycle"] for e in candidate["offices"].values() if e.get("cycle")})
        if cycle is not None and cycle not in candidate["cycles"]:
            candidate["cycles"] = sorted(candidate["cycles"] + [cycle])

        for kind, detail in pending_flags:
            # A site ID settles identity, so don't second-guess it on a long gap.
            if kind == "cycle_gap" and candidate.get("filer_id"):
                continue
            _add_review_flag(store, new_flags, cid, kind, detail, now)

        fresh_office_fields = {field: record.get(field) for field in _UPDATABLE_OFFICE_FIELDS}
        fresh_office_fields["cycle"] = cycle
        existing_office = candidate["offices"].get(office)
        label = f"{name} -- {office}"

        if existing_office is None:
            new_office_entry = dict(fresh_office_fields)
            new_office_entry["first_seen"] = now
            new_office_entry["last_seen"] = now
            candidate["offices"][office] = new_office_entry
            if not is_new_candidate:
                new_offices.append(label)
            continue

        old_cycle = existing_office.get("cycle")
        if cycle is not None and old_cycle is not None and cycle != old_cycle:
            # Same office, later cycle: keep the earlier filing as history.
            snapshot = {f: existing_office.get(f) for f in _UPDATABLE_OFFICE_FIELDS + ("first_seen", "last_seen")}
            existing_office.setdefault("history", []).append(snapshot)
            existing_office["first_seen"] = now
            label += f" (cycle {old_cycle} -> {cycle})"

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

    store[_COLLISIONS_KEY] = sorted(known_collisions)
    save_candidate_store(site, store, store_dir)

    return {
        "new_candidates": new_candidates,
        "new_offices": new_offices,
        "updated_offices": updated_offices,
        "unchanged": unchanged,
        "collisions": collision_labels,
        "review": new_flags,
        "open_review": sum(1 for f in store.get(_REVIEW_KEY, []) if f.get("status") == "open"),
        "store": store,
    }
