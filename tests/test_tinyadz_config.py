from pathlib import Path

MK_PAGES_WITH_RAIL_AD = [
    "web/src/pages/mk/archive.astro",
    "web/src/pages/mk/subjekt/[name].astro",
    "web/src/pages/mk/analize.astro",
    "web/src/pages/mk/about.astro",
    "web/src/pages/mk/methodology.astro",
    "web/src/pages/mk/editorial.astro",
    "web/src/pages/mk/support.astro",
    "web/src/pages/mk/tema/[topic].astro",
    "web/src/pages/mk/cluster/[slug].astro",
]

MK_PAGES_WITH_INLINE_AD = [
    "web/src/pages/mk/for-you.astro",
    "web/src/pages/mk/izvori.astro",
    "web/src/pages/mk/graf.astro",
    "web/src/pages/mk/pulse.astro",
    "web/src/pages/mk/tema/[topic].astro",
]

SHARED_COMPONENTS_WITH_AD = [
    "web/src/components/home/HomeRail.astro",
    "web/src/components/briefing/BriefingSidebar.astro",
]


def test_tinyadz_helper_module_exists():
    helper = Path("web/src/lib/tinyadz.ts")
    assert helper.exists()
    source = helper.read_text(encoding="utf-8")
    assert "scripts/v2.0/main.js" in source
    assert "6a2995c32b7233c34b097a9c" in source


def test_layout_wires_tinyadz_for_mk():
    layout = Path("web/src/layouts/Layout.astro").read_text(encoding="utf-8")
    script = Path("web/src/components/TinyAdzScript.astro").read_text(encoding="utf-8")
    assert "TinyAdzScript" in layout
    assert 'site-id={siteId}' in script
    assert 'data-site-id={siteId}' in script
    assert "transition:persist" in script
    assert "requestNextAd" in script


def test_tinyadz_inlined_container_component():
    component = Path("web/src/components/TinyAdzInlinedAd.astro").read_text(encoding="utf-8")
    assert 'ta-ad-container=""' in component
    assert "shouldLoadTinyAdz" in component


def test_tinyadz_rail_wrapper_exists():
    rail = Path("web/src/components/TinyAdzRailAd.astro").read_text(encoding="utf-8")
    assert "TinyAdzInlinedAd" in rail
    assert "page-rail-ad" in rail


def test_mk_content_pages_include_tinyadz_slots():
    for path in MK_PAGES_WITH_RAIL_AD:
        source = Path(path).read_text(encoding="utf-8")
        assert "TinyAdzRailAd" in source, path

    for path in MK_PAGES_WITH_INLINE_AD:
        source = Path(path).read_text(encoding="utf-8")
        assert "TinyAdzInlinedAd" in source, path

    for path in SHARED_COMPONENTS_WITH_AD:
        source = Path(path).read_text(encoding="utf-8")
        assert "TinyAdzRailAd" in source, path


def test_production_config_documents_tinyadz_site_id():
    example = Path("deploy/production_config.example").read_text(encoding="utf-8")
    assert "PUBLIC_TINYADZ_SITE_ID=6a2995c32b7233c34b097a9c" in example
    assert "PUBLIC_TINYADZ_TEST_MODE=false" in example
