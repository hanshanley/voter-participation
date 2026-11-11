"""Exercise the actual self-contained parish map on desktop and phone, without network."""

import argparse
import hashlib
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    proofs = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for name, viewport in (("desktop", dict(width=1280, height=1000)),
                    ("phone", dict(width=390, height=844))):
                context = browser.new_context(viewport=viewport, offline=True)
                page = context.new_page()
                errors, requests = [], []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("request", lambda request: requests.append(request.url) if request.url.startswith(("http:", "https:")) else None)
                page.goto(args.map.resolve().as_uri())
                page.wait_for_selector("path.parish")
                assert page.locator("path.parish").count() == 64
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert page.evaluate("""() => {
                  const controls=[...document.querySelectorAll('.controls select,.controls button')].map(node=>node.getBoundingClientRect());
                  return controls.every((a,i)=>controls.slice(i+1).every(b=>
                    Math.min(a.right,b.right)<=Math.max(a.left,b.left) ||
                    Math.min(a.bottom,b.bottom)<=Math.max(a.top,b.top)));
                }"""), "Map controls overlap"
                expected = page.evaluate("JSON.parse(document.getElementById('source-data').textContent)")
                cell_checks = 0
                for group in ("WHITE", "BLACK", "OTHER", "MALE", "FEMALE", "INPER", "ABS"):
                    page.select_option("#group", group)
                    for metric in ("share", "count"):
                        page.select_option("#metric", metric)
                        for feature in expected["features"]:
                            key, counts = feature["id"], feature["properties"]["native_source_profile"]["raw_counts"]
                            path = page.locator(f'path[data-key="{key}"]')
                            path.focus()
                            page.keyboard.press("Enter")
                            assert page.locator("#place").inner_text() == feature["properties"]["reference"]["name"]
                            assert f"{counts[group]:,}" in page.locator("#description").inner_text()
                            expected_value = (f"{counts[group]:,}" if metric == "count" else
                                f"{float(next(r['source_composition_pct'] for r in feature['properties']['native_compositions'] if r['native_group'] == group)):.1f}%")
                            assert page.locator("#value").inner_text() == expected_value
                            assert path.get_attribute("aria-pressed") == "true"
                            cell_checks += 1
                pointer_checks = 0
                for feature in expected["features"]:
                    key = feature["id"]
                    path = page.locator(f'path[data-key="{key}"]')
                    path.scroll_into_view_if_needed()
                    point = path.evaluate("""node => {
                      const r=node.getBoundingClientRect();
                      for (const step of [12,35,80]) for(let y=0;y<step;y++) for(let x=0;x<step;x++){
                        const px=r.left+(x+.5)*r.width/step,py=r.top+(y+.5)*r.height/step;
                        if(document.elementFromPoint(px,py)===node)return {x:px,y:py};
                      }
                      return null;
                    }""")
                    assert point is not None, f"No actual pointer hit for {key}"
                    page.mouse.click(point["x"], point["y"])
                    assert page.locator("#place").inner_text() == feature["properties"]["reference"]["name"]
                    pointer_checks += 1
                page.click("#reset")
                assert page.locator("#place").inner_text() == "Louisiana \u00b7 all parishes"
                assert page.locator('path[aria-pressed="true"]').count() == 0
                page.select_option("#group", "FEMALE")
                page.select_option("#metric", "share")
                assert "278 arithmetic units" in page.locator("#residual").inner_text()
                page.locator("summary").click()
                assert "four differ" in page.locator(".method").inner_text()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                assert not errors and not requests, (errors, requests)
                page.locator("summary").click()
                page.locator("#group").evaluate("node=>node.blur()")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(args.output.with_name(args.output.stem + "-" + name + ".png")), full_page=True)
                proofs.append(dict(screen=name, keyboard_group_metric_cells=cell_checks,
                    actual_pointer_county_selections=pointer_checks, no_horizontal_overflow=True,
                    controls_do_not_overlap=True,
                    source_state_parent_reset=True, all_native_values_checked=True,
                    browser_errors=errors, external_requests=requests))
                context.close()
        finally:
            browser.close()
    body = args.map.read_bytes()
    result = dict(status="passed_offline_louisiana_group_map", screens=["desktop", "phone"],
        map_pin=dict(bytes=len(body), sha256=hashlib.sha256(body).hexdigest()),
        proofs=proofs, valid_source_data_overrides=False)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
