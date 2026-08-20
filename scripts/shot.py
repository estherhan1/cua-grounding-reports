import sys
from playwright.sync_api import sync_playwright
out = sys.argv[1] if len(sys.argv) > 1 else "/local3/yuhan/tmp/a3dash/shot.png"
theme = sys.argv[2] if len(sys.argv) > 2 else "light"
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 2000},
                    color_scheme=theme, device_scale_factor=1)
    pg.goto("file:///local3/yuhan/tmp/a3_webarena_dashboard.html", wait_until="load")
    pg.wait_for_timeout(1500)
    pg.screenshot(path=out, full_page=False)
    pg.screenshot(path=out.replace(".png", "_full.png"), full_page=True)
    print("ok", pg.title())
    b.close()
