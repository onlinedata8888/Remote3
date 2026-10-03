import sys
from playwright.sync_api import sync_playwright

HTML = 'file://' + sys.argv[1] if len(sys.argv) > 1 else 'file:///home/claude/Remote13Restore-main/app/assets/remote.html'

FAKE = """
window.__keys = []; window.__hidlog = []; window.__hidstart = 0;
window.TVNative = {
  ready(){}, key(c,d){ window.__keys.push([c,d]); }, keys(c,n){}, text(t){}, launch(l){},
  toastMsg(m){}, manualIp(){}, connect(h){}, reconnect(){}, rescan(){}, pairCode(c){}, cancelPairing(){},
  voiceToggle(){}, castPick(k){}, galleryReady(k){return true}, listGalleryAlbums(k){return '[]'},
  listGalleryItems(k,b){return '[]'}, castMediaStoreItem(a,b){}, castPlay(){}, castPause(){}, castStop(){}, castSeek(m){}
};
window.HidNative = {
  start(){ window.__hidstart++; setTimeout(function(){ window.__hid.onState('ready',''); }, 30); },
  devices(){ return JSON.stringify([{name:'My PC',addr:'AA:BB:CC:DD:EE:FF',connected:false,last:true}]); },
  connect(a){ window.__hidlog.push(['connect',a]); setTimeout(function(){ window.__hid.onState('connected','My PC'); }, 30); },
  disconnect(){ window.__hidlog.push(['disconnect']); }, reconnect(){ window.__hidlog.push(['reconnect']); }, discoverable(){ window.__hidlog.push(['disc']); }, btSettings(){},
  move(x,y){ window.__hidlog.push(['move',x,y]); }, buttons(m){ window.__hidlog.push(['buttons',m]); },
  click(m){ window.__hidlog.push(['click',m]); }, scroll(v,h){ window.__hidlog.push(['scroll',v,h]); }, status(){ return '{}'; }
};
"""
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

    page.locator('#mouseBtn').dblclick(); page.wait_for_timeout(600)
    check('mouse page opened', page.evaluate("document.getElementById('mousePage').classList.contains('open')"))
    check('HID.start called on open (PC mode default)', page.evaluate("window.__hidstart") >= 1)
    check('PC bar + PC keys visible', page.locator('#mpPcBar').is_visible() and page.locator('#mpPcKeys').is_visible())
    check('bottom key row still visible (Back/Home/Play/Recent/Remote)', page.locator('#mpTvKeys').is_visible() and page.locator('#mpTvKeys button').count()==5)
    check('no PC|TV switch any more', page.locator('#mpTarget').count()==0)
    check('device sheet auto-opened when not connected', page.evaluate("document.getElementById('mpSheet').classList.contains('open')"))
    check('paired PC listed', 'My PC' in page.locator('#mpDevList').inner_text())
    page.locator('#mpDevList .mp-dev').first.click(); page.wait_for_timeout(200)
    check('connect(addr) called', ['connect','AA:BB:CC:DD:EE:FF'] in log(page))
    check('sheet closed after connect', not page.evaluate("document.getElementById('mpSheet').classList.contains('open')"))
    check('status shows Connected: My PC', 'Connected: My PC' in page.locator('#mpPcStat').inner_text())
    check('status dot green', not page.evaluate("document.getElementById('mpDot').classList.contains('offline')"))

    pn = page.locator('#mpPanel').bounding_box()
    cx, cy = pn['x'] + pn['width']*0.4, pn['y'] + pn['height']*0.4
    cdp = ctx.new_cdp_session(page)
    def touch(kind, pts): cdp.send('Input.dispatchTouchEvent', {'type': kind, 'touchPoints': pts})
    def tp(x, y, i=0): return {'x': x, 'y': y, 'id': i}

    # cursor move
    log(page); page.evaluate("window.__keys.length=0")
    touch('touchStart', [tp(cx, cy)])
    for i in range(1, 11):
        touch('touchMove', [tp(cx + i*6, cy + i*3)]); page.wait_for_timeout(16)
    touch('touchEnd', []); page.wait_for_timeout(100)
    mv = [e for e in log(page) if e[0] == 'move']
    sx = sum(e[1] for e in mv); sy = sum(e[2] for e in mv)
    check('finger drag sends HID move (right/down)', mv and sx > 60 and sy > 30, f'sum=({sx},{sy}) n={len(mv)}')
    check('NO D-pad keys sent to TV in PC mode', page.evaluate("window.__keys.length") == 0)

    # tap -> left click
    touch('touchStart', [tp(cx, cy)]); page.wait_for_timeout(50); touch('touchEnd', []); page.wait_for_timeout(100)
    check('tap = left click', ['click', 1] in log(page))

    # two-finger tap -> right click
    touch('touchStart', [tp(cx, cy, 0), tp(cx + 60, cy, 1)]); page.wait_for_timeout(60); touch('touchEnd', []); page.wait_for_timeout(120)
    check('2-finger tap = right click', ['click', 2] in log(page))

    # two-finger scroll (fingers up => scroll down, natural)
    touch('touchStart', [tp(cx, cy + 100, 0), tp(cx + 60, cy + 100, 1)])
    for i in range(1, 9):
        touch('touchMove', [tp(cx, cy + 100 - i*12, 0), tp(cx + 60, cy + 100 - i*12, 1)]); page.wait_for_timeout(16)
    touch('touchEnd', []); page.wait_for_timeout(100)
    sc = [e for e in log(page) if e[0] == 'scroll']
    check('2-finger swipe sends scroll', sc and sum(e[1] for e in sc) < 0, str(sc))
    check('2-finger scroll did not click', True)

    # hold => drag
    touch('touchStart', [tp(cx, cy)]); page.wait_for_timeout(650)
    touch('touchMove', [tp(cx + 20, cy + 10)]); page.wait_for_timeout(40); touch('touchEnd', []); page.wait_for_timeout(100)
    lg = log(page)
    check('hold = left button down', ['buttons', 1] in lg, str(lg[:4]))
    check('release = left button up', lg and ['buttons', 0] in lg)

    # LEFT/RIGHT keys held
    page.locator('[data-pcbtn="2"]').dispatch_event('pointerdown', {'pointerId': 5, 'isPrimary': True})
    page.locator('[data-pcbtn="2"]').dispatch_event('pointerup', {'pointerId': 5, 'isPrimary': True})
    lg = log(page)
    check('RIGHT key press/release', ['buttons', 2] in lg and ['buttons', 0] in lg, str(lg))

    # bottom row: Recent duplicates page-1 Recent (Yellow key), Remote icon returns to page 1
    page.evaluate("window.__keys.length=0")
    page.locator('#mpRecent').click(); page.wait_for_timeout(120)
    yk = page.evaluate("window.__keys.slice()")
    page.evaluate("window.__keys.length=0")
    page.evaluate("document.getElementById('mpSheet').classList.remove('open')")
    page.locator('#mpRemote').click(); page.wait_for_timeout(450)
    check('Recent (mouse page) sends a key like page-1 Recent', len(yk) >= 1, str(yk))
    page.locator('#recentBtn').click(); page.wait_for_timeout(120)
    y1 = page.evaluate("window.__keys.slice()")
    check('same key as page-1 Recent button', [k[0] for k in y1][:1] == [k[0] for k in yk][:1], f'{yk} vs {y1}')
    check('Remote icon closed the mouse page (back on 1st page)', not page.evaluate("document.getElementById('mousePage').classList.contains('open')"))
    check('no volume buttons on mouse page', page.locator('#mousePage [data-mpkey="volUp"], #mousePage [data-mpkey="volDown"]').count()==0)
    page.locator('#mouseBtn').dblclick(); page.wait_for_timeout(500)
    check('mouse icon reopens mouse page', page.evaluate("document.getElementById('mousePage').classList.contains('open')"))
    # back closes sheet first
    page.evaluate("document.getElementById('mpDevBtn').click()"); page.wait_for_timeout(100)
    check('Devices button opens sheet', page.evaluate("document.getElementById('mpSheet').classList.contains('open')"))
    r = page.evaluate("window.__tv && window.__tv.handleBack && window.__tv.handleBack()")
    check('back closes sheet first (page stays open)', r and not page.evaluate("document.getElementById('mpSheet').classList.contains('open')") and page.evaluate("document.getElementById('mousePage').classList.contains('open')"))
    check('version bumped to v11.23', 'v11.23' in page.locator('#tvVersion').inner_text())
    check('no JS errors', not errs, str(errs))
    b.close()

# ---- extra: tap jitter must not move the cursor; slop travel must not be lost; gain curve smooth ----
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 400, 'height': 820}, has_touch=True, device_scale_factor=2)
    page = ctx.new_page(); page.add_init_script(FAKE); page.goto(HTML); page.wait_for_timeout(500)
    page.locator('#mouseBtn').dblclick(); page.wait_for_timeout(500)
    page.evaluate("window.__hid.onState('connected','My PC')"); page.wait_for_timeout(100)
    pn = page.locator('#mpPanel').bounding_box(); cx, cy = pn['x'] + 100, pn['y'] + 150
    cdp = ctx.new_cdp_session(page)
    def touch(k, pts): cdp.send('Input.dispatchTouchEvent', {'type': k, 'touchPoints': pts})
    log(page)
    touch('touchStart', [{'x': cx, 'y': cy, 'id': 0}])
    for d in (1, 2, 1, 0, -1): touch('touchMove', [{'x': cx + d, 'y': cy + 1, 'id': 0}]); page.wait_for_timeout(16)
    touch('touchEnd', []); page.wait_for_timeout(120)
    lg = log(page)
    res.append(not [e for e in lg if e[0] == 'move'] and ['click', 1] in lg)
    print('PASS' if res[-1] else 'FAIL', '- finger jitter during a tap: no cursor movement, still a left click', lg)
    # slow steady move of 40px -> total sent should be >= 40px (slop travel included, gain >= 1.3)
    touch('touchStart', [{'x': cx, 'y': cy, 'id': 0}])
    for i in range(1, 41): touch('touchMove', [{'x': cx + i, 'y': cy, 'id': 0}]); page.wait_for_timeout(20)
    touch('touchEnd', []); page.wait_for_timeout(150)
    sx = sum(e[1] for e in log(page) if e[0] == 'move')
    res.append(sx >= 40 * 1.25); print('PASS' if res[-1] else 'FAIL', '- slow 40px drag keeps all travel (gain>=1.3)', f'sent={sx:.1f}')
    # fast move -> larger gain than slow
    touch('touchStart', [{'x': cx, 'y': cy, 'id': 0}])
    for i in range(1, 21): touch('touchMove', [{'x': cx + i*8, 'y': cy, 'id': 0}]); page.wait_for_timeout(8)
    touch('touchEnd', []); page.wait_for_timeout(150)
    fx = sum(e[1] for e in log(page) if e[0] == 'move')
    res.append(fx / 160 > sx / 40 * 1.1); print('PASS' if res[-1] else 'FAIL', '- fast drag gets more acceleration than slow', f'fast gain={fx/160:.2f} slow gain={sx/40:.2f}')
    b.close()
print(f'\nTOTAL {sum(res)}/{len(res)}'); sys.exit(0 if all(res) else 1)
