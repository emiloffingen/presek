from pathlib import Path


def test_hilltopads_helper_module():
    helper = Path("web/src/lib/hilltopads.ts").read_text(encoding="utf-8")
    assert "listActiveHilltopZones" in helper
    assert "multitag-inpage" in helper
    assert "bWXdVfs.duGmlX0" in helper
    assert "HILLTOPADS_VERIFICATION_TOKEN_LIVE" in helper
    assert "HILLTOPADS_VERIFICATION_TOKEN_MK" in helper
    assert "d07d1cfa2d1d864d0e56d9b80842c7dde3a1d1a8" in helper
    assert "hilltopAdsVerificationToken" in helper


def test_layout_wires_hilltopads_zones():
    layout = Path("web/src/layouts/Layout.astro").read_text(encoding="utf-8")
    component = Path("web/src/components/HilltopAdsZone.astro").read_text(encoding="utf-8")
    assert "HilltopAdsZone" in layout
    assert "listActiveHilltopZones" in layout
    assert "hilltopAdsVerificationToken" in layout
    assert 'name="referrer" content="no-referrer-when-downgrade"' in layout
    assert "data-hilltop-zone" in component


def test_production_config_documents_hilltopads():
    example = Path("deploy/production_config.example").read_text(encoding="utf-8")
    assert "PUBLIC_HILLTOPADS_MULTITAG_INPAGE_ENABLED=true" in example
    assert "PUBLIC_HILLTOPADS_POPUNDER_ENABLED=false" in example
    assert "PUBLIC_HILLTOPADS_MULTITAG_ENABLED=false" in example
