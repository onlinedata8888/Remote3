import os,sys,subprocess,time,json
from playwright.sync_api import sync_playwright
HTML='file:///home/claude/work/remote.html'
FAKE=open('/home/claude/Remote13Restore-main/tests/test_gamepad_custom.py').read().split('FAKE = """')[1].split('"""')[0]
res=[]
def check(n,c,x=''): res.append(bool(c)); print('PASS' if c else 'FAIL','-',n,x)
log=open('/tmp/server.log','w')
srv=subprocess.Popen([sys.executable,'-u','/home/claude/pc/gamepad_server.py','--dry-run','--port','18765','--pin','4321'],stdout=log,stderr=subprocess.STDOUT)
time.sleep(1)
def L(): log.flush(); return open('/tmp/server.log').read()
try:
  with sync_playwright() as pw:
    b=pw.chromium.launch(); ctx=b.new_context(viewport={'width':800,'height':380},has_touch=True); ctx.add_init_script(FAKE)
    pg=ctx.new_page(); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
    # --- wrong PIN first
    pg.goto(HTML); pg.evaluate("localStorage.setItem('remote13_gp_mode','wifi');localStorage.setItem('remote13_gp_ip','127.0.0.1');localStorage.setItem('remote13_gp_port','18765');localStorage.setItem('remote13_gp_pin','0000')")
    pg.reload(); pg.wait_for_timeout(400)
    pg.evaluate("document.getElementById('moreGamepad').click()"); pg.wait_for_timeout(1900)
    check('chip says WiFi', pg.evaluate("document.getElementById('gpMode').textContent")=='WiFi')
    st=pg.evaluate("document.getElementById('gpStat').textContent"); check('wrong PIN is refused (status shows retry)', 'WiFi' in st and 'connected' not in st.lower().replace('connect ho','').replace('connect nahi',''), st)
    check('server created no pad for wrong PIN', 'player' not in L(), L())
    # --- right PIN
    pg.evaluate("localStorage.setItem('remote13_gp_pin','4321')"); pg.wait_for_timeout(2600)
    st=pg.evaluate("document.getElementById('gpStat').textContent"); check('connected with right PIN', 'PC se connected' in st and 'Player 1' in st, st)
    check('server saw player 1', 'player 1' in L())
    pg.evaluate("document.getElementById('gpSheet').classList.remove('open')")
    cdp=ctx.new_cdp_session(pg)
    def center(js): return pg.evaluate("(function(){var r=%s.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2];})()"%js)
    def el(kind,key=None): return "(function(){var it=__gpTest.items.filter(function(x){return x.t==='%s'%s;})[0];return it.el;})()"%(kind,(" && x.b==='%s'"%key) if key else '')
    def td(x,y,i=0): cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y,'id':i}]})
    def tu(): cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
    x,y=center(el('round','A')); td(x,y); pg.wait_for_timeout(300)
    check('A press arrives at PC', 'btn=0000000000000001' in L(), L()[-200:])
    tu(); pg.wait_for_timeout(300)
    x2,y2=center(el('round','B')); xa,ya=center(el('round','A')); td(x2,y2,0); td(xa,ya,1); pg.wait_for_timeout(300)
    check('A+B together (multi-touch)', 'btn=0000000000000011' in L())
    cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]}); pg.wait_for_timeout(300)
    check('release arrives', L().strip().splitlines()[-1].find('btn=0000000000000000')>0, L().strip().splitlines()[-1])
    # stick
    sx,sy=center(el('stick')); td(sx,sy); pg.wait_for_timeout(100)
    cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':sx+200,'y':sy,'id':0}]}); pg.wait_for_timeout(400)
    last=[l for l in L().splitlines() if 'btn=' in l][-1]; check('stick right -> positive X', 'L=(127,' in last or 'R=(127,' in last, last); tu(); pg.wait_for_timeout(300)
    # idle keep-alive for >3s with server timeout 15
    n0=len(L().splitlines()); pg.wait_for_timeout(3500); check('heartbeat keeps sending while idle', len(L().splitlines())>n0)
    # server restart -> app auto reconnects
    srv.terminate(); srv.wait(); time.sleep(0.5)
    srv=subprocess.Popen([sys.executable,'-u','/home/claude/pc/gamepad_server.py','--dry-run','--port','18765','--pin','4321'],stdout=log,stderr=subprocess.STDOUT)
    pg.wait_for_timeout(5500); st=pg.evaluate("document.getElementById('gpStat').textContent"); check('auto-reconnect after PC restart', 'PC se connected' in st, st)
    # switch chip: wifi -> tv -> bt
    pg.click('#gpMode'); pg.wait_for_timeout(200); check('chip -> TV keys', pg.evaluate("document.getElementById('gpMode').textContent")=='TV keys')
    pg.wait_for_timeout(500); check('leaving WiFi closes socket', 'disconnected' in L())
    pg.click('#gpMode'); pg.wait_for_timeout(300); check('chip -> BT', pg.evaluate("document.getElementById('gpMode').textContent")=='BT')
    # BT path still sends to HID
    pg.evaluate("window.__pad.length=0"); pg.evaluate("document.getElementById('gpSheet').classList.remove('open')")
    x,y=center(el('round','A')); td(x,y); pg.wait_for_timeout(250); tu()
    check('BT mode still goes to HidNative', any(p[0]&1 for p in pg.evaluate("window.__pad")))
    check('no JS errors', not errs, errs); b.close()
finally:
  srv.terminate()
print(sum(res),'/',len(res)); sys.exit(0 if all(res) else 1)
