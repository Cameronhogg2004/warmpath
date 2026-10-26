"""The code checks between the Scout and the Verifier: invented claims never get through."""
import json

from warmpath.agents import check_candidates, surname
from warmpath.models import Candidate, ScoutReport, Tie
from warmpath.tools import Deps


def _deps():
    d = Deps(run_id="test", company="Medtronic", aliases=["Medtronic", "Covidien"])
    d.add("trial", "https://clinicaltrials.gov/study/NCT06777368", "Redo TAVR",
          json.dumps({"nct": "NCT06777368", "yale_site_people": ["John Forrest (principal investigator)"]}), 2025)
    d.add("paper", "https://pubmed.ncbi.nlm.nih.gov/1/", "Old paper",
          json.dumps({"yale_authors": ["Vora AN"], "company_authors": ["X (Medtronic)"]}), 2015)
    d.add("directory", "https://medicine.yale.edu/profile/naftali-kaminski/", "Naftali Kaminski",
          json.dumps({"name": "Naftali Kaminski", "title": "Boehringer Ingelheim Pharmaceuticals, Inc. Professor of Medicine"}))
    return d


def _run(*cands):
    events = []
    kept, dropped = check_candidates(ScoutReport(candidates=list(cands)), _deps(), events.append)
    return kept, {d["name"]: d["reason"] for d in dropped}


def test_a_grounded_trial_tie_is_kept_and_gets_the_directory_email():
    kept, dropped = _run(Candidate(name="John K. Forrest", ties=[Tie(type="clinical_trial", description="PI", source_ids=["S1"])]))
    assert not dropped and kept[0]["email"] == "john.k.forrest@yale.edu"
    assert kept[0]["profile_url"].startswith("https://medicine.yale.edu/profile/")


def test_a_made_up_source_id_is_dropped():
    kept, dropped = _run(Candidate(name="John K. Forrest", ties=[Tie(type="clinical_trial", description="PI", source_ids=["S99"])]))
    assert not kept and "does not exist" in dropped["John K. Forrest"]


def test_a_person_the_source_does_not_name_is_dropped():
    kept, dropped = _run(Candidate(name="Harlan Krumholz", ties=[Tie(type="clinical_trial", description="PI", source_ids=["S1"])]))
    assert not kept and "does not mention" in dropped["Harlan Krumholz"]


def test_an_old_paper_is_not_a_current_tie():
    kept, dropped = _run(Candidate(name="Amit N. Vora", ties=[Tie(type="co_publication", description="paper", source_ids=["S2"])]))
    assert not kept and "older than" in dropped["Amit N. Vora"]


def test_a_named_chair_must_name_the_company():
    kept, dropped = _run(Candidate(name="Naftali Kaminski", ties=[Tie(type="named_chair", description="chair", source_ids=["S3"])]))
    assert not kept and "does not mention the company" in dropped["Naftali Kaminski"]


def test_pubmed_style_names_resolve():
    assert surname("Forrest JK") == surname("John K. Forrest, MD") == "forrest"
