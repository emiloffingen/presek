from core.copy_quality import assess_mk_copy_purity, mk_bundle_passes_publish_gate


def test_mk_copy_rejects_serbian_latin_sports_leak():
    text = (
        "Vo meč pomeđu Holandija i Japonija rezultatot beše 2:2, "
        "a vo vtoro poluvreme se odvijaše intenziven fudbal."
    )
    diag = assess_mk_copy_purity(text)
    assert diag["ok"] is False
    assert diag["leaks"]


def test_mk_copy_accepts_clean_cyrillic_editorial():
    text = (
        "Холандија и Јапонија го поделија поенот во натпреварот со резултат 2:2. "
        "Изворите потврдуваат дека второто полувреме беше интензивно, "
        "но останува нејасно кој тим ќе напредува понатаму."
    )
    diag = assess_mk_copy_purity(text)
    assert diag["ok"] is True
    assert diag["score"] >= 0.8


def test_mk_bundle_gate_uses_combined_fields():
    ok, diag = mk_bundle_passes_publish_gate(
        headline="Холандија и Јапонија",
        summary="Натпреварот заврши со резултат 2:2.",
        article="Медиумите се согласуваат околу текот на натпреварот.",
        key_facts=["Резултат: 2:2"],
    )
    assert ok is True
    assert diag["reason"] == "ok"
