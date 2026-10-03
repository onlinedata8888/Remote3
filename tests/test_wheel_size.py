"""v11.29.2: side wheels as thick as the bottom wheel; wheels identical + working in PC mouse-pad mode."""
import sys
from playwright.sync_api import sync_playwright
HTML = 'file://' + sys.argv[1]
FAKE = open(__file__.replace('test_wheel_size.py', 'test_hid_pc_mode.py')).read().split('FAKE = "\"\"')[1].split('"\"\"')[0]
res=[]
def check(n,c,x=''): res.append(bool(c)); print('PASS' if c else 'FAIL','-',n,x)
with sync_playwright() as p:
    b=p.chromium.launch()
    for vw in (360,400,430):
        ctx=b.new_context(viewport={'width':vw,'height':820},has_touch=True); page=ctx.new_page()
        page.add_init_script(FAKE); page.goto(HTML); page.wait_for_timeout(400)
        bb=lambda i: page.locator(i).bounding_box()
        def snap(): return {k:bb('#'+k) for k in ('wheelV','wheelVR','wheelH')}
        s=snap()
        check(f'{vw}: left wheel width == bottom wheel height', abs(s['wheelV']['width']-s['wheelH']['height'])<0.6, (s['wheelV']['width'],s['wheelH']['height']))
        check(f'{vw}: red wheel width == bottom wheel height', abs(s['wheelVR']['width']-s['wheelH']['height'])<0.6)
        page.locator('#mouseBtn').click(); page.wait_for_timeout(500)
        check(f'{vw}: PC mode on', 'pcpad' in page.evaluate("document.querySelector('#touchpad').className"))
        s2=snap()
        check(f'{vw}: wheels same size/place in PC mode', all(abs(s[k][f]-s2[k][f])<0.6 for k in s for f in ('x','y','width','height')))
        page.evaluate("window.__hidlog.splice(0)")
        for wid,ax in (('wheelV','y'),('wheelH','x')):
            w=bb('#'+wid); cx=w['x']+w['width']/2; cy=w['y']+w['height']/2
            page.mouse.move(cx,cy); page.mouse.down()
            for i in range(1,30): page.mouse.move(cx+(i*4 if ax=='x' else 0), cy+(i*4 if ax=='y' else 0))
            page.mouse.up()
        log=page.evaluate("window.__hidlog.splice(0)")
        check(f'{vw}: both wheels send PC scroll in PC mode', len(log)>=2, log[:3])
        ctx.close()
    b.close()
sys.exit(0 if all(res) else 1)
