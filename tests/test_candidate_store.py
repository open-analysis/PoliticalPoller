"""Scenario tests for candidate_store.py identity handling (filer IDs,
corroboration/splits, cycles, review flags). Run: python3 tests/test_candidate_store.py
(or pytest)."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "PoliticalPoller"))
import candidate_store as cs

def rec(name, office="Governor", party="DFL", site="https://janedoe.com", date="05/26/2026", fid=None, state="Minnesota"):
    return {"site":"mn","state":state,"office_level":"State","office":office,"candidate_name":name,
            "party":party,"website":site,"file_date":date,"filer_id":fid,"source_url":"u","scraped_at":"t"}

def fresh(): return tempfile.mkdtemp()
def run(d, recs, **kw): return cs.upsert_candidates("mn", recs, store_dir=d, **kw)
def cands(store): return [c for c in store.values() if isinstance(c, dict)]
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or (c or sys.exit(1))

def test_candidate_store():
    # cycle parsing
    ok(cs._extract_cycle({"file_date":"05/26/2026"})==2026 and cs._extract_cycle({"file_date":"2026-05-26"})==2026
       and cs._extract_cycle({"file_date":"5/26/26"})==2026 and cs._extract_cycle({"file_date":""}) is None, "cycle parsing")
    ok(cs._website_domain("https://www.JaneDoe.com/x")=="janedoe.com" and cs._website_domain("N/A")=="" , "domain parsing")

    # 1. filer IDs
    d=fresh()
    run(d,[rec("Pat Lee","Governor",fid="A1"), rec("Pat Lee","Senator",fid="B2")])
    s=cs.load_candidate_store("mn",d)
    ok(len(cands(s))==2, "same name, different filer IDs -> two candidates, no collision")
    r=run(d,[rec("Patricia Lee","Governor",fid="A1")])   # name respelled, same ID
    s=r["store"]; ok(len(cands(s))==2 and r["new_candidates"]==[], "same ID, respelled name -> same candidate")
    # adoption of name-only record
    d=fresh(); run(d,[rec("Sam Roe","Auditor")]); r=run(d,[rec("Sam Roe","Auditor",fid="Z9")])
    c=cands(r["store"]); ok(len(c)==1 and c[0]["filer_id"]=="Z9", "ID adopted onto earlier name-only record")

    # 2. corroboration
    d=fresh(); run(d,[rec("Al Kim","Governor",party="DFL",site="https://alkim.com",date="05/01/2022")])
    r=run(d,[rec("Al Kim","Senator",party="DFL",site="https://alkim.com",date="05/01/2024")])
    ok(len(cands(r["store"]))==1 and not r["review"], "no conflict -> merged silently")
    d=fresh(); run(d,[rec("Al Kim","Governor",party="DFL",site="https://alkim.com",date="05/01/2022")])
    r=run(d,[rec("Al Kim","Senator",party="GOP",site="https://alkim.com",date="05/01/2024")])
    ok(len(cands(r["store"]))==1 and [f["kind"] for f in r["review"]]==["party_changed"], "party only -> merged + party_changed flag")
    d=fresh(); run(d,[rec("Al Kim","Governor",party="DFL",site="https://alkim.com",date="05/01/2022")])
    r=run(d,[rec("Al Kim","Senator",party="GOP",site="https://other.org",date="05/01/2024")])
    s=r["store"]
    ok(len(cands(s))==2 and "al kim|minnesota" in s["_collisions"] and r["collisions"]
       and "split_conflict" in [f["kind"] for f in r["review"]], "party+website differ -> split, collisions list, flags")
    r2=run(d,[rec("Al Kim","Governor",party="DFL",site="https://alkim.com",date="05/01/2022"),
              rec("Al Kim","Senator",party="GOP",site="https://other.org",date="05/01/2024")])
    ok(len(cands(r2["store"]))==2 and r2["new_candidates"]==[] and r2["unchanged"]==2, "re-run after split: no duplicates")
    d=fresh(); run(d,[rec("Al Kim","Governor",party="DFL",site="https://alkim.com",date="05/01/2022")])
    r=run(d,[rec("Al Kim","Senator",party="GOP",site="https://alkim.com",date="05/01/2024")],split_policy="either")
    ok(len(cands(r["store"]))==2, "split_policy='either' splits on one conflict")
    # same filing refreshed with party correction: no flags/no split
    d=fresh(); run(d,[rec("Al Kim","Governor",party="DFL")]); r=run(d,[rec("Al Kim","Governor",party="GOP")])
    ok(len(cands(r["store"]))==1 and not r["review"] and r["updated_offices"]==["Al Kim -- Governor"], "same office+cycle correction -> plain update")

    # 3. cycles / gap / history
    d=fresh(); r=run(d,[rec("Bo Tan","Mayor",date="05/01/2010")])
    ok(cands(r["store"])[0]["cycles"]==[2010] and cands(r["store"])[0]["offices"]["Mayor"]["cycle"]==2010, "cycle stored per office and candidate")
    r=run(d,[rec("Bo Tan","Mayor",date="05/01/2026")])
    c=cands(r["store"])[0]
    ok(len(cands(r["store"]))==1 and c["cycles"]==[2010,2026] and len(c["offices"]["Mayor"]["history"])==1
       and [f["kind"] for f in r["review"]]==["cycle_gap"] or print(r["review"]), "same office later cycle: history kept + cycle_gap flag")
    r=run(d,[rec("Bo Tan","Mayor",date="05/01/2026")]); ok(not r["review"], "flag not repeated")

    # 4. review list / dismiss
    fl=cs.list_review_flags("mn",store_dir=d); ok(len(fl)==1, "list_review_flags")
    ok(cs.dismiss_review_flag("mn",fl[0]["flag_id"],"checked",store_dir=d) and not cs.list_review_flags("mn",store_dir=d), "dismiss")
    r=run(d,[rec("Bo Tan","Mayor",date="05/01/2010"),rec("Bo Tan","Mayor",date="05/01/2026")]); ok(not r["review"], "dismissed flag stays dismissed")

    # old-format store compat (no cycles key) + search_by_name ignoring _review
    d=fresh(); cid=cs.candidate_hash("Old Timer","Minnesota"); cs.save_candidate_store("mn",{cid:{"candidate_id":cid,"candidate_name":"Old Timer","state":"Minnesota","site":"mn","offices":{"X":{"party":"DFL","website":"https://o.com","file_date":"01/01/2012","first_seen":"a","last_seen":"a"}}}},d)
    r=run(d,[rec("Old Timer","Y",party="DFL",site="https://o.com",date="05/01/2026")])
    ok(len(cs.search_by_name(r["store"],"old"))>=1 and any(f["kind"]=="cycle_gap" for f in r["review"]) , "old-format store handled; search ignores _review")
    print("ALL PASS")


if __name__ == "__main__":
    test_candidate_store()
