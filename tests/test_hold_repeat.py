import sys
from playwright.sync_api import sync_playwright
HTML='file:///home/claude/Remote13Restore-main/app/assets/remote.html'
FAKE="""window.__keys=[];window.TVNative={ready(){},key(c,d){window.__keys.push([c,d,Date.now()])},keys(c,n){},text(t){},launch(l){},toastMsg(m){},manualIp(){},connect(h){},reconnect(){},rescan(){},pairCode(c){},cancelPairing(){},voiceToggle(){},castPick(k){},galleryReady(k){return true},listGalleryAlbums(k){return '[]'},listGalleryItems(k,b){return '[]'},castMediaStoreItem(a,b){},castPlay(){},castPause(){},castStop(){},castSeek(m){}};"""
res=[]
def check(n,c,x=''): res.append(bool(c)); print('PASS' if c else 'FAIL','-',n,x)
def ks(page): return page.evaluate("window.__keys.splice(0)")
with sync_playwright() as p:
    b=p.chromium.launch(); ctx=b.new_context(viewport={'width':400,'height':820},has_touch=True,device_scale_factor=2)
    page=ctx.new_page(); errs=[]; page.on('pageerror',lambda e:errs.append(str(e)))
    page.add_init_script(FAKE); page.goto(HTML); page.wait_for_timeout(500)
    cdp=ctx.new_cdp_session(page)
    def touch(k,pts): cdp.send('Input.dispatchTouchEvent',{'type':k,'touchPoints':pts})
    # --- fast forward hold
    ff=page.locator('[data-key="forward"]').first; bb=ff.bounding_box(); x,y=bb['x']+bb['width']/2,bb['y']+bb['height']/2
    ks(page); touch('touchStart',[{'x':x,'y':y,'id':0}]); page.wait_for_timeout(1300); touch('touchEnd',[]); page.wait_for_timeout(200)
    r=ks(page); n=[k for k in r if k[0]==90]
    check('FF hold repeats (many key sends)', len(n)>=5, f'{len(n)} sends')
    page.wait_for_timeout(400); check('FF stops after release', not ks(page))
    # quick tap = exactly one
    touch('touchStart',[{'x':x,'y':y,'id':0}]); page.wait_for_timeout(60); touch('touchEnd',[]); page.wait_for_timeout(250)
    r=ks(page); check('FF quick tap = single press', len([k for k in r if k[0]==90])==1, str(r))
    # after a hold, next quick tap on another button must still work
    rw=page.locator('[data-key="rewind"]').first; bb=rw.bounding_box()
    touch('touchStart',[{'x':bb['x']+bb['width']/2,'y':bb['y']+bb['height']/2,'id':0}]); page.wait_for_timeout(60); touch('touchEnd',[]); page.wait_for_timeout(250)
    check('rewind tap works', len([k for k in ks(page) if k[0]==89])==1)
    # --- touchpad hold
    tp=page.locator('#touchpad').bounding_box(); cx,cy=tp['x']+tp['width']/2,tp['y']+tp['height']*0.6
    for name,(dx,dy),code in [('right',(80,0),22),('left',(-80,0),21),('down',(0,80),20),('up',(0,-80),19)]:
        ks(page); touch('touchStart',[{'x':cx,'y':cy,'id':0}])
        for i in range(1,9): touch('touchMove',[{'x':cx+dx*i/8,'y':cy+dy*i/8,'id':0}]); page.wait_for_timeout(15)
        page.wait_for_timeout(1000); touch('touchEnd',[]); page.wait_for_timeout(150)
        n=[k for k in ks(page) if k[0]==code]; check(f'touchpad swipe+hold {name} repeats', len(n)>=5, f'{len(n)}')
        page.wait_for_timeout(300); check(f'{name} stops on release', not ks(page))
    # plain swipe without hold = one step; tap = OK
    ks(page); touch('touchStart',[{'x':cx,'y':cy,'id':0}])
    for i in range(1,9): touch('touchMove',[{'x':cx+60*i/8,'y':cy,'id':0}]); page.wait_for_timeout(10)
    touch('touchEnd',[]); page.wait_for_timeout(500)
    check('quick swipe = 1 step only', len([k for k in ks(page) if k[0]==22])==1)
    touch('touchStart',[{'x':cx,'y':cy,'id':0}]); page.wait_for_timeout(50); touch('touchEnd',[]); page.wait_for_timeout(200)
    check('tap = OK', any(k[0]==23 for k in ks(page)))
    check('v11.23', 'v11.23' in page.locator('#tvVersion').inner_text()); check('no JS errors', not errs, str(errs)); b.close()
print(sum(res),'/',len(res)); sys.exit(0 if all(res) else 1)
