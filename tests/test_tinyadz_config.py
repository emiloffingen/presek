from pathlib import Path

# MK-only Astro routes (full page files under pages/mk/)
MK_PAGES_WITH_RAIL_AD = [
    "web/src/pages/mk/subjekt/[name].astro",
    "web/src/pages/mk/tema/[topic].astro",
]

MK_PAGES_WITH_INLINE_AD = [
    "web/src/pages/mk/subjekt/[name].astro",
    "web/src/pages/mk/tema/[topic].astro",
]

# Shared root pages serve presek.mk via host-based lang (see localePaths MK_SHARED_ROOT_PATHS)
SHARED_MK_HOST_PAGES_WITH_RAIL_AD = [
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

SHARED_MK_HOST_PAGES_WITH_INLINE_AD = [
    "web/src/pages/for-you.astro",
    "web/src/pages/izvori.astro",
    "web/src/pages/graf.astro",
    "web/src/pages/pulse.astro",
    "web/src/pages/tema/[topic].astro",
    "web/src/pages/briefing.astro",
    "web/src/pages/archive.astro",
    "web/src/pages/subjekt/[name].astro",
]

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
    "web/src/pages/graf.astro",
    "web/src/pages/grafik.astro",
    "web/src/pages/pulse.astro",
    "web/src/pages/tema/[topic].astro",
    "web/src/pages/briefing.astro",
    "web/src/pages/archive.astro",
    "web/src/pages/subjekt/[name].astro",
]

SHARED_COMPONENTS_WITH_AD = [
    "web/src/components/home/HomeRail.astro",
    "web/src/components/home/HomePage.astro",
    "web/src/components/home/HomeUnifiedFeed.astro",
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
    assert "TINYADZ_SCRIPT_URL" in script
    assert "setAttribute('site-id', siteId)" in script
    assert "setAttribute('data-site-id', siteId)" in script
    assert "data-tinyadz-loader" in script
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


def test_mk_only_content_pages_include_tinyadz_slots():
    for path in MK_PAGES_WITH_RAIL_AD:
        source = Path(path).read_text(encoding="utf-8")
        assert "TinyAdzRailAd" in source, path

    for path in MK_PAGES_WITH_INLINE_AD:
        source = Path(path).read_text(encoding="utf-8")
        assert "TinyAdzInlinedAd" in source, path


def test_shared_mk_host_pages_include_tinyadz_slots():
    for path in SHARED_MK_HOST_PAGES_WITH_RAIL_AD:
        source = Path(path).read_text(encoding="utf-8")
        assert "TinyAdzRailAd" in source, path

    for path in SHARED_MK_HOST_PAGES_WITH_INLINE_AD:
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
        assert "TinyAdz" in source, path


def test_production_config_documents_tinyadz_site_ids():
    example = Path("deploy/production_config.example").read_text(encoding="utf-8")
    assert "PUBLIC_TINYADZ_SITE_ID=6a2995c32b7233c34b097a9c" in example
    assert "PUBLIC_TINYADZ_LIVE_SITE_ID=6a29a71de09ffcc4c9bbd83e" in example
    assert "PUBLIC_TINYADZ_TEST_MODE=false" in example
