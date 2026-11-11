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
            page.locator("#participation-model summary").click()
            page.wait_for_function("!document.querySelector('#model-dimension').disabled")
            page.select_option("#model-dimension", "race")
            page.wait_for_function(
                "document.querySelector('#model-summary').textContent.includes('Race / ethnicity')"
            )
            assert page.locator("#model-rows tr").count() == 5
            page.select_option("#model-dimension", "education")
            page.wait_for_function(
                "document.querySelector('#model-summary').textContent.includes('Education')"
            )
            assert page.locator("#model-rows tr").count() == 7
            assert "No modeled 2026" in page.locator("#participation-model").inner_text()
            page.locator("#participation-model summary").click()
            page.locator("#participation-cps summary").click()
            page.wait_for_function("!document.querySelector('#cps-dimension').disabled")
            assert page.locator("#cps-rows tr").count() == 2
            assert "14.12%" in page.locator("#cps-rows").inner_text()
            page.select_option("#cps-dimension", "race_ethnicity")
            assert page.locator("#cps-rows tr").count() == 10
            assert "White, non-Hispanic" in page.locator("#cps-rows").inner_text()
            page.select_option("#cps-dimension", "education")
            assert page.locator("#cps-rows tr").count() == 10
            page.locator("#participation-cps summary").click()
            page.locator("#nc-current-chart li").first.wait_for()
            assert page.locator("#nc-current-county option").count() == 101
            assert page.locator("#nc-current-chart li").count() == 8
            assert "Not a live feed" in page.locator("#nc-current-asof").inner_text()
            page.select_option("#nc-current-county", "WAKE")
            page.select_option("#nc-current-dimension", "sex")
            page.select_option("#nc-current-method", "EARLY VOTING")
            assert page.locator("#nc-current-chart li").count() == 3
            assert "WAKE" in page.locator("#nc-current-county-note").inner_text()
            assert "not demographic turnout rates" in page.locator("#nc-current-group-note").inner_text()
            response = page.request.get(page.locator("#nc-current-complete").evaluate("element => element.href"))
            assert response.ok
            assert response.body().startswith(b"PK")
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
