"""Customizable game pad: play (buttons/dpad/stick -> HID report), TV keys mode, edit (move/resize/add/delete), persistence."""
import os, json
from playwright.sync_api import sync_playwright

HTML = 'file://' + os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'app', 'assets', 'remote.html'))
FAKE = """
window.__pad = []; window.__keys = [];
window.TVNative = { ready(){}, key(c,d){ window.__keys.push([c,d]); }, keys(){}, text(){}, launch(){}, toastMsg(){}, manualIp(){}, connect(){}, reconnect(){}, rescan(){},
  pairCode(){}, cancelPairing(){}, voiceToggle(){}, castPick(){}, galleryReady(){return true;}, listGalleryAlbums(){return '[]';}, listGalleryItems(){return '[]';},
  castMediaStoreItem(){}, castPlay(){}, castPause(){}, castStop(){}, castSeek(){}, setOrientation(m){} };
window.HidNative = { pad(b,h,lx,ly,rx,ry){ window.__pad.push([b,h,lx,ly,rx,ry]); }, start(){}, status(){ return JSON.stringify({state:'connected',name:'TV',profile:1}); },
  devices(){ return JSON.stringify([{name:'Living TV',addr:'AA:BB',connected:true,last:true}]); }, connect(){}, reconnect(){}, getProfile(){ return 1; }, setProfile(p){ window.__prof = p; },
  forget(a){ window.__forgot = a; return true; }, discoverable(){}, btSettings(){}, move(){}, buttons(){}, click(){}, scroll(){}, key(){}, zoom(){}, disconnect(){} };
"""
res = []
def check(n, c, x=''):
    res.append(bool(c)); print('PASS' if c else 'FAIL', '-', n, x)

with sync_playwright() as pw:
    b = pw.chromium.launch()
    ctx = b.new_context(viewport={'width': 800, 'height': 380}, has_touch=True)
    ctx.add_init_script(FAKE)
    pg = ctx.new_page(); errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.goto(HTML); pg.wait_for_timeout(500)
    pg.evaluate("document.getElementById('moreGamepad').click()")
    pg.wait_for_timeout(1700)
    check('overlay open', pg.evaluate("document.getElementById('gpOverlay').classList.contains('show')"))
    n = pg.evaluate("__gpTest.items.length"); check('default layout has controls', n >= 14, n)
    pg.evaluate("document.getElementById('gpSheet').classList.remove('open')")

    def center(sel_js):
        return pg.evaluate("(function(){var r=%s.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2];})()" % sel_js)
    def item_el(kind, key=None):
        return "(function(){var it=__gpTest.items.filter(function(x){return x.t==='%s'%s;})[0];return it.el;})()" % (kind, (" && x.b==='%s'" % key) if key else '')
    def press(cx, cy, pid=1):
        cdp = ctx.new_cdp_session(pg); return cdp
    cdp = ctx.new_cdp_session(pg)
    def tdown(x, y, i=0): cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': x, 'y': y, 'id': i}]})
    def tmove(x, y, i=0): cdp.send('Input.dispatchTouchEvent', {'type': 'touchMove', 'touchPoints': [{'x': x, 'y': y, 'id': i}]})
    def tup(): cdp.send('Input.dispatchTouchEvent', {'type': 'touchEnd', 'touchPoints': []})

    # --- play: A button
    x, y = center(item_el('round', 'A')); pg.evaluate("window.__pad=[]")
    tdown(x, y); pg.wait_for_timeout(80)
    st = pg.evaluate("__gpTest.state()"); check('A pressed -> bit0', st['btn'] == 1, st)
    check('report sent to HID', pg.evaluate("window.__pad.length") > 0)
    tup(); pg.wait_for_timeout(80)
    check('A released', pg.evaluate("__gpTest.state().btn") == 0)
    # --- play: X (bit3) and L1 (bit6)
    x, y = center(item_el('round', 'X')); tdown(x, y); pg.wait_for_timeout(60)
    check('X -> bit3', pg.evaluate("__gpTest.state().btn") == 8); tup(); pg.wait_for_timeout(60)
    x, y = center(item_el('pill', 'L1')); tdown(x, y); pg.wait_for_timeout(60)
    check('L1 -> bit6', pg.evaluate("__gpTest.state().btn") == 64); tup(); pg.wait_for_timeout(60)
    # --- dpad up, then slide to up-right
    x, y = center(item_el('dpad')); r = pg.evaluate("__gpTest.items.filter(function(i){return i.t==='dpad'})[0].w") / 2
    tdown(x, y - r * 0.7); pg.wait_for_timeout(60); check('dpad up -> hat 1', pg.evaluate("__gpTest.state().hat") == 1)
    tmove(x + r * 0.6, y - r * 0.6); pg.wait_for_timeout(60); check('dpad slide -> up-right hat 2', pg.evaluate("__gpTest.state().hat") == 2)
    tup(); pg.wait_for_timeout(60); check('dpad released', pg.evaluate("__gpTest.state().hat") == 0)
    # --- left stick right
    sx, sy = center("(function(){return __gpTest.items.filter(function(i){return i.t==='stick'&&i.side==='L'})[0].el;})()")
    sr = pg.evaluate("__gpTest.items.filter(function(i){return i.t==='stick'&&i.side==='L'})[0].w") / 2
    tdown(sx, sy); tmove(sx + sr, sy); pg.wait_for_timeout(60)
    ax = pg.evaluate("__gpTest.state().ax"); check('left stick right -> lx>100', ax[0] > 100 and abs(ax[1]) < 10, ax)
    tup(); pg.wait_for_timeout(60); check('stick centred', pg.evaluate("__gpTest.state().ax") == [0, 0, 0, 0])
    # --- multi touch: A + B together
    ax_, ay_ = center(item_el('round', 'A')); bx_, by_ = center(item_el('round', 'B'))
    cdp.send('Input.dispatchTouchEvent', {'type': 'touchStart', 'touchPoints': [{'x': ax_, 'y': ay_, 'id': 1}, {'x': bx_, 'y': by_, 'id': 2}]}); pg.wait_for_timeout(80)
    check('A+B multitouch', pg.evaluate("__gpTest.state().btn") == 3, pg.evaluate("__gpTest.state().btn")); tup(); pg.wait_for_timeout(60)

    # --- TV keys mode
    pg.evaluate("document.getElementById('gpMode').click()"); pg.wait_for_timeout(100); pg.evaluate("window.__keys=[]")
    x, y = center(item_el('round', 'A')); tdown(x, y); pg.wait_for_timeout(80); tup(); pg.wait_for_timeout(80)
    keys = pg.evaluate("window.__keys"); check('TV mode: A -> key 96 down/up', [96, 1] in keys and [96, 2] in keys, keys)
    pg.evaluate("window.__keys=[]"); x, y = center(item_el('dpad')); tdown(x, y - r * 0.7); pg.wait_for_timeout(60); tup(); pg.wait_for_timeout(60)
    keys = pg.evaluate("window.__keys"); check('TV mode: dpad up -> key 19', [19, 1] in keys and [19, 2] in keys, keys)
    pg.evaluate("document.getElementById('gpMode').click()"); pg.wait_for_timeout(100)

    # --- edit mode: move
    pg.evaluate("document.getElementById('gpEdit').click()"); pg.wait_for_timeout(100)
    check('edit mode on', pg.evaluate("document.getElementById('gpOverlay').classList.contains('edit')"))
    before = pg.evaluate("(function(){var i=__gpTest.items.filter(function(x){return x.b==='B'})[0];return [i.x,i.y,i.s];})()")
    x, y = center(item_el('round', 'B'))
    tdown(x, y); tmove(x - 60, y + 20); tmove(x - 120, y + 40); tup(); pg.wait_for_timeout(100)
    after = pg.evaluate("(function(){var i=__gpTest.items.filter(function(x){return x.b==='B'})[0];return [i.x,i.y,i.s];})()")
    check('drag moves button', after[0] < before[0] - 0.05 and after[1] > before[1], (before, after))
    check('button selected after drag', pg.evaluate("document.getElementById('gpOverlay').classList.contains('hassel')"))
    # resize by slider
    pg.evaluate("var s=document.getElementById('giSize');s.value=40;s.dispatchEvent(new Event('input'))")
    check('slider resizes', abs(pg.evaluate("__gpTest.items.filter(function(x){return x.b==='B'})[0].s") - 0.40) < 0.01)
    # resize by corner handle
    cx, cy = center(item_el('round', 'B')); hx, hy = pg.evaluate("(function(){var h=document.querySelector('.gp-handle').getBoundingClientRect();return [h.left+h.width/2,h.top+h.height/2];})()")
    tdown(hx, hy); tmove(hx + 40, hy + 40); tup(); pg.wait_for_timeout(100)
    check('handle enlarges', pg.evaluate("__gpTest.items.filter(function(x){return x.b==='B'})[0].s") > 0.45)
    # rebind + label
    pg.evaluate("var s=document.getElementById('giBind');s.value='R3';s.dispatchEvent(new Event('change'))")
    check('rebind to R3', pg.evaluate("__gpTest.items.filter(function(x){return x.lab==='R3'})[0].b") == 'R3')
    # delete
    n0 = pg.evaluate("__gpTest.items.length"); pg.evaluate("document.getElementById('giDel').click()")
    check('delete removes', pg.evaluate("__gpTest.items.length") == n0 - 1)
    # add
    pg.evaluate("document.querySelector('#gpEditBar [data-a=add]').click()"); pg.wait_for_timeout(50)
    check('add sheet shows', pg.evaluate("document.getElementById('gpSheet').classList.contains('open')"))
    pg.evaluate("document.querySelectorAll('#gpSheet button')[1].click()"); pg.wait_for_timeout(50)
    check('pill added', pg.evaluate("__gpTest.items.length") == n0 and pg.evaluate("__gpTest.items[__gpTest.items.length-1].t") == 'pill')
    # persistence
    pg.evaluate("document.querySelector('#gpEditBar [data-a=done]').click()")
    saved = pg.evaluate("JSON.parse(localStorage.getItem('remote13_gp_layout_land')).items.length"); check('layout saved', saved == n0, saved)
    pg.evaluate("document.getElementById('gpClose').click()"); pg.wait_for_timeout(200)
    pg.evaluate("document.getElementById('moreGamepad').click()"); pg.wait_for_timeout(1700)
    check('layout restored after reopen', pg.evaluate("__gpTest.items.length") == n0)
    # reset
    pg.evaluate("__gpTest.edit(true)"); 
    pg.evaluate("var b=document.querySelector('#gpEditBar [data-a=reset]');b.click();b.click()"); pg.wait_for_timeout(100)
    check('reset restores default', pg.evaluate("__gpTest.items.length") >= 14)
    # bluetooth sheet: profile + forget
    pg.evaluate("__gpTest.edit(false)"); pg.evaluate("document.getElementById('gpStat').click()"); pg.wait_for_timeout(100)
    check('BT sheet opens', pg.evaluate("document.getElementById('gpSheet').classList.contains('open')"))
    pg.evaluate("Array.from(document.querySelectorAll('#gpSheet button')).filter(function(b){return /Mouse \\+ Keyboard/.test(b.textContent)})[0].click()")
    check('profile switch calls native', pg.evaluate("window.__prof") == 0)
    pg.evaluate("document.querySelector('#gpSheet button.forget').click()"); check('forget calls native', pg.evaluate("window.__forgot") == 'AA:BB')
    # portrait layout
    pg.evaluate("document.getElementById('gpClose').click()"); pg.set_viewport_size({'width': 380, 'height': 800}); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('moreGamepad').click()"); pg.wait_for_timeout(1700)
    pg.evaluate("document.getElementById('gpRot').click()"); pg.wait_for_timeout(1800)
    nport = pg.evaluate("__gpTest.items.length"); check('portrait layout built', nport >= 14, nport)
    inb = pg.evaluate("__gpTest.items.every(function(i){return i.cx>=0&&i.cx<=document.getElementById('gpStage').clientWidth&&i.cy>=0&&i.cy<=document.getElementById('gpStage').clientHeight})")
    check('all controls inside stage (portrait)', inb)
    check('no JS errors', not errs, errs)
    pg.screenshot(path='/tmp/gp_portrait.png')
    b.close()
print('\n%d/%d passed' % (sum(res), len(res)))
raise SystemExit(0 if all(res) else 1)
