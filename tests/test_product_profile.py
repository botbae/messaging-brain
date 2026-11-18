from product_profile import (
    DecisionDict,
    ProductProfile,
    score_brain_strength,
    suggest_brain_improvements,
)


def _profile(**kw):
    base = dict(product="Acme", audience="founders", problem="messy copy", advantage="fast")
    base.update(kw)
    return ProductProfile(**base)


def test_plain_dict_decisions_are_normalised():
    # Regression: POST /brain crashed when decisions was a plain dict.
    p = _profile(decisions={"icp": "founders"})
    assert isinstance(p.decisions, DecisionDict)
    assert p.decisions.get_entry("icp")["value"] == "founders"


def test_suggestions_and_strength_run_on_plain_dict_decisions():
    p = _profile(decisions={"icp": "founders", "primary_problem": "messy copy"})
    assert isinstance(suggest_brain_improvements(p), list)
    assert isinstance(score_brain_strength(p), dict)


def test_save_and_load_round_trip(tmp_path):
    p = _profile()
    p.decisions.set_entry("icp", "seed-stage founders", confidence=0.6, source_notes="guess")
    path = tmp_path / "clients" / "acme" / "product_profile.json"
    p.save(path)

    loaded = ProductProfile.load(path)
    assert loaded.product == "Acme"
    assert loaded.brain_version == 1
    assert loaded.decisions.get_entry("icp") == {
        "value": "seed-stage founders",
        "confidence": 0.6,
        "source_notes": "guess",
    }
    assert list((path.parent / "brain_history").glob("*_v1.json"))
