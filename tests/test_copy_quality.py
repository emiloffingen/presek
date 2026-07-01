from core.copy_quality import assess_sr_copy_purity, copy_bundle_passes_publish_gate


def test_sr_copy_rejects_cyrillic_heavy_text():
    text = "Влада Србије је данас усвојила измене закона о правосуђу и изборима."
    diag = assess_sr_copy_purity(text)
    assert diag["ok"] is False
    assert diag["reason"] in {"high_cyrillic_share", "low_latin", "cyrillic_leaks"}


def test_sr_copy_accepts_latin_editorial():
    text = (
        "Vlada Srbije je danas usvojila izmene zakona o pravosuđu. "
        "Izvori se razlikuju oko roka primene, ali potvrđuju osnovne izmene."
    )
    diag = assess_sr_copy_purity(text)
    assert diag["ok"] is True


def test_copy_bundle_gate_respects_lang():
    ok_sr, _ = copy_bundle_passes_publish_gate(
        lang="sr",
        headline="Vlada Srbije",
        summary="Izvori potvrđuju promene.",
        article="Posledice ostaju nejasne za lokalne vlasti.",
    )
    ok_mk, diag_mk = copy_bundle_passes_publish_gate(
        lang="mk",
        headline="Холандија",
        summary="Vo meč rezultatot beše 2:2.",
        article="Vo vtoro poluvreme se odvijaše intenziven fudbal.",
    )
    assert ok_sr is True
    assert ok_mk is False
    assert diag_mk["reason"] in {"high_latin_share", "serbian_latin_leaks", "low_cyrillic"}
