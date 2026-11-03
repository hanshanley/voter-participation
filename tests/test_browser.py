import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scripts.build import ROOT


def test_local_explorer_filters_maps_and_offline_assets():
    if not (ROOT / "public/data/analysis.json").exists():
        pytest.skip("Build analysis artifacts before browser validation")
    from playwright.sync_api import sync_playwright

    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT / "public"))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    errors = []
    external = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 1000})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: external.append(request.url)
                    if not request.url.startswith("http://127.0.0.1:") else None)
            page.goto(f"http://127.0.0.1:{server.server_port}")
            page.locator("#visualization svg").wait_for()
            assert page.locator("#year").input_value() == "2024"
            page.select_option("#dimension", "education")
            page.locator("#visualization svg").wait_for()
            assert "not available" not in page.locator("#notice").inner_text()
            page.select_option("#year", "1998")
            assert "not available" in page.locator("#notice").inner_text()
            page.select_option("#basis", "vap")
            page.locator("#visualization svg").wait_for()
            page.select_option("#year", "2024")
            page.click("button[data-view='states']")
            assert page.locator(".map-feature").count() == 51
            page.select_option("#type", "midterm")
            assert page.locator("#year").input_value() == "2022"
            assert "midterm" in page.locator("#title").inner_text()
            page.click("button[data-view='precincts']")
            page.locator(".map-feature").first.wait_for()
            assert page.locator(".map-feature").count() > 2000
            page.select_option("#type", "all")
            page.select_option("#year", "2024")
            page.wait_for_function(
                "document.querySelector('#title').textContent.includes('2024')"
            )
            page.locator(".map-feature").first.wait_for()
            assert page.locator(".map-feature").count() > 2000
            page.select_option("#dimension", "race")
            page.select_option("#group", "Black")
            page.wait_for_function("document.querySelector('#title').textContent.includes('Black')")
            page.select_option("#year", "2004")
            page.wait_for_function(
                "document.querySelector('#notice').textContent.includes('We do not substitute a different year')"
            )
            assert page.locator(".map-feature").count() == 0
            page.click("button[data-view='coverage']")
            assert page.locator(".map-feature").count() == 51
            assert "not assessed" in page.locator("#notice").inner_text()
            page.set_viewport_size({"width": 390, "height": 844})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert not errors, errors
            assert not external, external
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
