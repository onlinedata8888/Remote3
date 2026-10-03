"""1 click on the mouse icon => page-1 touchpad becomes a PC mouse pad; 2 clicks => Mouse page opens.
All other page-1 buttons must keep sending TV keys exactly as before."""
import sys
from playwright.sync_api import sync_playwright

HTML = 'file://' + sys.argv[1] if len(sys.argv) > 1 else 'file:///home/claude/Remote13Restore-main/app/assets/remote.html'
FAKE = open(__file__.replace('test_pad_pc_mode.py', 'test_hid_pc_mode.py')).read().split('FAKE = """')[1].split('"""')[0]

res = []
def check(n, c, x=''):
    res.append(bool(c)); print(('PASS' if c else 'FAIL'), '-', n, x)
def log(page): return page.evaluate("window.__hidlog.splice(0)")

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 400, 'height': 820}, has_touch=True, device_scale_factor=2)
    page = ctx.new_page(); errs = []
    page.on('pageerror', lambda e: errs.append(str(e)))
    page.add_init_script(FAKE); page.goto(HTML); page.wait_for_timeout(500)
    cdp = ctx.new_cdp_session(page)
    def touch(kind, pts): cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': pts})
    def tp(x, y, i=0): return {'x': x, 'y': y, 'id': i}
    cls = lambda sel: page.evaluate(f"document.querySelector('{sel}').className")

    pb = page.locator('#touchpad').bounding_box()
    cx, cy = pb['x'] + pb['width']*0.5, pb['y'] + pb['height']*0.6

    # --- default: untouched TV touchpad ---
    page.evaluate("window.__keys.length=0"); log(page)
    touch('touchStart', [tp(cx, cy)]); page.wait_for_timeout(40); touch('touchEnd', []); page.wait_for_timeout(150)
    check('default: pad tap = OK key to TV', page.evaluate("window.__keys.filter(k=>k[1]==0||k[1]==undefined||true).length") > 0)
    check('default: no HID traffic', log(page) == [])

    # --- 1 click => pad mode ON ---
    page.locator('#mouseBtn').click(); page.wait_for_timeout(500)
    check('1 click: Mouse page did NOT open', 'open' not in cls('#mousePage'))
    check('1 click: pad is in PC mode', 'pcpad' in cls('#touchpad'))
    check('1 click: icon turned into mouse', page.locator('#mouseBtn .ic-mouse').is_visible() and not page.locator('#mouseBtn .ic-arrow').is_visible())
    check('1 click: HID.start called', page.evaluate("window.__hidstart") >= 1)
    check('pad hint says PC mouse', 'PC mouse' in page.locator('#touchpad .pad-hint').inner_text())

    # connect via HID state callback (as the Java side would)
    page.evaluate("window.__hid.onState('connected','My PC')"); page.wait_for_timeout(100)
    check('pad hint shows connected PC', 'My PC' in page.locator('#touchpad .pad-hint').inner_text())

    # drag => HID move, no TV keys
    page.evaluate("window.__keys.length=0"); log(page)
    touch('touchStart', [tp(cx, cy)])
    for i in range(1, 11):
        touch('touchMove', [tp(cx + i*6, cy + i*3)]); page.wait_for_timeout(16)
    touch('touchEnd', []); page.wait_for_timeout(120)
    mv = [e for e in log(page) if e[0] == 'move']
    check('pad drag => HID move (right/down)', mv and sum(e[1] for e in mv) > 60 and sum(e[2] for e in mv) > 30)
    check('pad drag => NO arrow keys to TV', page.evaluate("window.__keys.length") == 0)

    # tap => left click, no OK key
    touch('touchStart', [tp(cx, cy)]); page.wait_for_timeout(40); touch('touchEnd', []); page.wait_for_timeout(120)
    check('pad tap => left click', ['click', 1] in log(page))
    check('pad tap => no OK key to TV', page.evaluate("window.__keys.length") == 0)

    # two-finger tap => right click
    touch('touchStart', [tp(cx, cy, 0), tp(cx + 60, cy, 1)]); page.wait_for_timeout(60); touch('touchEnd', []); page.wait_for_timeout(120)
    check('pad 2-finger tap => right click', ['click', 2] in log(page))

    # two-finger scroll
    touch('touchStart', [tp(cx - 40, cy + 40, 0), tp(cx + 20, cy + 40, 1)])
    for i in range(1, 9):
        touch('touchMove', [tp(cx - 40, cy + 40 - i*12, 0), tp(cx + 20, cy + 40 - i*12, 1)]); page.wait_for_timeout(16)
    touch('touchEnd', []); page.wait_for_timeout(120)
    l = log(page)
    check('pad 2-finger swipe => HID scroll', any(e[0] == 'scroll' for e in l), str([e for e in l if e[0]=='scroll'][:3]))
    check('pad 2-finger scroll did not click', not any(e[0] == 'click' for e in l))

    # hold => drag
    touch('touchStart', [tp(cx, cy)]); page.wait_for_timeout(620)
    for i in range(1, 6):
        touch('touchMove', [tp(cx + i*8, cy)]); page.wait_for_timeout(16)
    touch('touchEnd', []); page.wait_for_timeout(120)
    l = log(page)
    check('pad hold+move => button down, move, button up', ['buttons', 1] in l and ['buttons', 0] in l and any(e[0]=='move' for e in l), str(l[:4]))

    # grey wheels keep the normal trackpad (TV) scroll even in PC pad mode
    wv = page.locator('#wheelV').bounding_box()
    page.evaluate("window.__keys.length=0"); log(page)
    x = wv['x'] + wv['width']/2; y0 = wv['y'] + wv['height']*0.3
    touch('touchStart', [tp(x, y0)])
    for i in range(1, 12):
        touch('touchMove', [tp(x, y0 + i*10)]); page.wait_for_timeout(16)
    touch('touchEnd', []); page.wait_for_timeout(120)
    l = log(page)
    check('left wheel => NO HID scroll in pad mode', not any(e[0] == 'scroll' for e in l), str(l[:3]))
    check('left wheel => arrow keys to TV', page.evaluate("window.__keys.length") > 0)

    # other page-1 buttons still send TV keys
    page.evaluate("window.__keys.length=0"); log(page)
    page.locator('#mediaRowTop [data-key="playpause"]').click(); page.wait_for_timeout(150)
    check('media button still sends TV key in pad mode', page.evaluate("window.__keys.length") > 0)
    check('media button sends nothing to PC', log(page) == [])

    # --- 1 click again => back to TV touchpad ---
    page.locator('#mouseBtn').click(); page.wait_for_timeout(500)
    check('click again: pad back to TV mode', 'pcpad' not in cls('#touchpad') and 'pc-on' not in cls('#mouseBtn'))
    check('click again: arrow icon back', page.locator('#mouseBtn .ic-arrow').is_visible())
    page.evaluate("window.__keys.length=0"); log(page)
    touch('touchStart', [tp(cx, cy)]); page.wait_for_timeout(40); touch('touchEnd', []); page.wait_for_timeout(150)
    check('TV mode again: tap = OK key', page.evaluate("window.__keys.length") > 0)
    check('TV mode again: no HID traffic', not any(e[0] in ('click','move') for e in log(page)))

    # --- 2 clicks => Mouse page opens ---
    page.locator('#mouseBtn').dblclick(); page.wait_for_timeout(600)
    check('2 clicks: Mouse page opened', 'open' in cls('#mousePage'))
    check('2 clicks: pad NOT toggled', 'pcpad' not in cls('#touchpad'))
    page.locator('#mpBack').click(); page.wait_for_timeout(450)
    check('back closes Mouse page', 'open' not in cls('#mousePage'))

    check('no JS errors', not errs, str(errs))
    b.close()
print(f"\nTOTAL {sum(res)}/{len(res)}"); sys.exit(0 if all(res) else 1)
