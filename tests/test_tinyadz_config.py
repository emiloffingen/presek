from pathlib import Path

MK_PAGES_WITH_RAIL_AD = [
    "web/src/pages/mk/archive.astro",
    "web/src/pages/mk/subjekt/[name].astro",
    "web/src/pages/mk/analize.astro",
    "web/src/pages/mk/editorial.astro",
    "web/src/pages/mk/tema/[topic].astro",
    "web/src/pages/mk/cluster/[slug].astro",
]

MK_PAGES_WITH_INLINE_AD = [
    "web/src/pages/mk/for-you.astro",
    "web/src/pages/mk/graf.astro",
    "web/src/pages/mk/tema/[topic].astro",
]

MK_MIRROR_PAGES = {
    "web/src/pages/mk/about.astro": ("web/src/pages/about.astro", "TinyAdzRailAd"),
    "web/src/pages/mk/methodology.astro": ("web/src/pages/methodology.astro", "TinyAdzRailAd"),
    "web/src/pages/mk/support.astro": ("web/src/pages/support.astro", "TinyAdzRailAd"),
    "web/src/pages/mk/pulse.astro": ("web/src/pages/pulse.astro", "TinyAdzInlinedAd"),
    "web/src/pages/mk/izvori.astro": ("web/src/pages/izvori.astro", "TinyAdzInlinedAd"),
}

LIVE_PAGES_WITH_RAIL_AD = [
    "web/src/pages/archive.astro",
    "web/src/pages/subjekt/[name].astro",
    "web/src/pages/analize.astro",
    "web/src/pages/about.astro",
    "web/src/pages/methodology.astro",
    "web/src/pages/editorial.astro",
    "web/src/pages/support.astro",
    "web/src/pages/tema/[topic].astro",
    "web/src/pages/cluster/[slug].astro",
]

LIVE_PAGES_WITH_INLINE_AD = [
    "web/src/pages/for-you.astro",
    "web/src/pages/izvori.astro",
    "web/src/pages/grafik.astro",
    "web/src/pages/pulse.astro",
    "web/src/pages/tema/[topic].astro",
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
    assert "6a29a71de09ffcc4c9bbd83e" in source


def test_layout_wires_tinyadz_for_mk_and_live():
    layout = Path("web/src/layouts/Layout.astro").read_text(encoding="utf-8")
    script = Path("web/src/components/TinyAdzScript.astro").read_text(encoding="utf-8")
    helper = Path("web/src/lib/tinyadz.ts").read_text(encoding="utf-8")
    assert "TinyAdzScript" in layout
    assert "shouldLoadTinyAdzScript" in layout
    assert "tinyAdzSiteId" in layout
    assert "siteId={tinyAdzSite}" in layout
    assert 'site-id={siteId}' in script
    assert 'data-site-id={siteId}' in script
    assert "transition:persist" in script
    assert "requestNextAd" in script
    assert "presek.live" in helper
    assert "presek.mk" in helper


def test_tinyadz_inlined_container_component():
    component = Path("web/src/components/TinyAdzInlinedAd.astro").read_text(encoding="utf-8")
    assert 'ta-ad-container=""' in component
    assert "shouldShowTinyAdzInlinedAds" in component


def test_tinyadz_rail_wrapper_exists():
    rail = Path("web/src/components/TinyAdzRailAd.astro").read_text(encoding="utf-8")
    assert "TinyAdzInlinedAd" in rail
    assert "page-rail-ad" in rail


def test_mk_mirror_pages_rewrite_to_live_templates_with_ads():
    for mk_path, (live_path, ad_component) in MK_MIRROR_PAGES.items():
        mk_source = Path(mk_path).read_text(encoding="utf-8")
        live_source = Path(live_path).read_text(encoding="utf-8")
        assert "Astro.rewrite" in mk_source, mk_path
        assert ad_component in live_source, live_path


def test_mk_content_pages_include_tinyadz_slots():
    for path in MK_PAGES_WITH_RAIL_AD:
        source = Path(path).read_text(encoding="utf-8")
        assert "TinyAdzRailAd" in source, path

    for path in MK_PAGES_WITH_INLINE_AD:
        source = Path(path).read_text(encoding="utf-8")
        assert "TinyAdzInlinedAd" in source, path


def test_live_content_pages_include_tinyadz_slots():
    for path in LIVE_PAGES_WITH_RAIL_AD:
        source = Path(path).read_text(encoding="utf-8")
        assert "TinyAdzRailAd" in source, path

    for path in LIVE_PAGES_WITH_INLINE_AD:
        source = Path(path).read_text(encoding="utf-8")
        assert "TinyAdzInlinedAd" in source, path


def test_shared_components_include_tinyadz_slots():
    for path in SHARED_COMPONENTS_WITH_AD:
        source = Path(path).read_text(encoding="utf-8")
        assert "TinyAdzRailAd" in source, path


def test_production_config_documents_tinyadz_site_ids():
    example = Path("deploy/production_config.example").read_text(encoding="utf-8")
    assert "PUBLIC_TINYADZ_SITE_ID=6a2995c32b7233c34b097a9c" in example
    assert "PUBLIC_TINYADZ_LIVE_SITE_ID=6a29a71de09ffcc4c9bbd83e" in example
    assert "PUBLIC_TINYADZ_TEST_MODE=false" in example
