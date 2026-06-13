from nlp.utils import extract_clean_summary_text, looks_like_leaked_json_fragment


def test_extract_clean_summary_text_unwraps_json_blob():
    assert extract_clean_summary_text('{"summary":"Cisto rezime","text":"Rezervno"}') == "Cisto rezime"


def test_extract_clean_summary_text_unwraps_truncated_json_blob():
    leaked = '{"summary":"Izvestaj austrijskog dnevnika *Standard* ukazuje na duboke veze'
    assert extract_clean_summary_text(leaked) == "Izvestaj austrijskog dnevnika Standard ukazuje na duboke veze"


def test_looks_like_leaked_json_fragment_detects_single_summary_key():
    assert looks_like_leaked_json_fragment('{"summary":"Tekst"}') is True
    assert looks_like_leaked_json_fragment("Obican tekst.") is False
