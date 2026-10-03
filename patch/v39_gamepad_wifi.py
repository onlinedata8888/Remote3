p='remote.html'
s=open(p,encoding='utf-8').read()
def rep(old,new,cnt=1):
    global s
    assert s.count(old)==cnt,(s.count(old),old[:90])
    s=s.replace(old,new)

# --- mode: bt | wifi | tv
rep("  var tvMode = lsGet('remote13_gp_mode') === 'tv';",
    "  var gpMode = lsGet('remote13_gp_mode'); if(gpMode !== 'tv' && gpMode !== 'wifi') gpMode = 'bt';\n  var tvMode = gpMode === 'tv', wifiMode = gpMode === 'wifi';")

# --- WiFi client (WebSocket -> PC receiver gamepad_server.py)
WF = r'''
  // ---------------------------------------------------------------- WiFi transport (phone -> PC receiver over WebSocket)
  // PC runs pc/gamepad_server.py; it turns every connected phone into a virtual Xbox 360 controller.
  var WF = { ws:null, state:'idle', want:false, retryT:0, connT:0, beatT:0, player:0, err:'' };
  function wfCfg(){ return { ip:(lsGet('remote13_gp_ip') || '').trim(), port:(lsGet('remote13_gp_port') || '8765').trim(), pin:(lsGet('remote13_gp_pin') || '').trim() }; }
  function wfSet(state, err){ WF.state = state; WF.err = err || ''; refresh(); if(state === 'connected') closeSheet(); }
  function wfClear(){ clearTimeout(WF.retryT); clearTimeout(WF.connT); clearInterval(WF.beatT); WF.retryT = WF.connT = WF.beatT = 0; }
  function wfClose(){
    WF.want = false; wfClear();
    var w = WF.ws; WF.ws = null; WF.player = 0;
    if(w){ w.onopen = w.onclose = w.onerror = w.onmessage = null; try{ w.close(); }catch(e){} }
    WF.state = 'idle'; WF.err = '';
  }
  function wfLine(){ return 'P ' + btn + ' ' + hatVal(hatDirs) + ' ' + ax[0] + ' ' + ax[1] + ' ' + ax[2] + ' ' + ax[3]; }
  function wfSend(){
    var w = WF.ws; if(!w || w.readyState !== 1) return;
    try{ w.send(wfLine()); }catch(e){}
  }
  function wfConnect(){
    var c = wfCfg();
    if(!c.ip){ wfSet('noip'); return; }
    wfClear();
    if(WF.ws){ var o = WF.ws; WF.ws = null; o.onopen = o.onclose = o.onerror = o.onmessage = null; try{ o.close(); }catch(e){} }
    WF.want = true; wfSet('connecting');
    var url = 'ws://' + c.ip + ':' + (c.port || '8765') + '/pad' + (c.pin ? '?pin=' + encodeURIComponent(c.pin) : '');
    var w;
    try{ w = new WebSocket(url); }catch(e){ wfSet('error', String(e && e.message || e)); wfRetry(); return; }
    WF.ws = w;
    WF.connT = setTimeout(function(){ if(WF.ws === w && w.readyState !== 1){ try{ w.close(); }catch(e){} wfFail(w, 'timeout'); } }, 5000);
    w.onopen = function(){
      if(WF.ws !== w) return;
      clearTimeout(WF.connT); WF.connT = 0;
      wfSet('connected');
      wfSend();
      clearInterval(WF.beatT); WF.beatT = setInterval(wfSend, 3000);     // keep-alive (server drops silent connections)
    };
    w.onmessage = function(e){ var m = /^OK (\d+)/.exec(String(e.data || '')); if(m){ WF.player = parseInt(m[1], 10); refresh(); } };
    w.onerror = function(){ };
    w.onclose = function(){ wfFail(w, WF.state === 'connected' ? 'lost' : 'refused'); };
  }
  function wfFail(w, why){
    if(WF.ws !== w) return;
    WF.ws = null; wfClear(); WF.player = 0;
    if(!WF.want) return;
    wfSet('error', why); wfRetry();
  }
  function wfRetry(){ clearTimeout(WF.retryT); WF.retryT = setTimeout(function(){ if(WF.want && wifiMode && ov.classList.contains('show')) wfConnect(); }, 2000); }
  function wfEnsure(){ WF.want = true; if(!WF.ws && WF.state !== 'connecting') wfConnect(); }
  function wifiSheet(){
    sheet.innerHTML = '';
    var c = wfCfg();
    sheet.appendChild(sh('PC (WiFi) GAME PAD'));
    sheet.appendChild(sp('PC par pc/gamepad_server.py chalao. Wo jo IP dikhaye woh yahan daalo. Phone aur PC same WiFi par hon.'));
    function field(label, key, ph, val, mode){
      var l = document.createElement('label'); l.style.cssText = 'display:flex;align-items:center;gap:8px;margin:6px 0;font-size:13px';
      var t = document.createElement('span'); t.textContent = label; t.style.cssText = 'flex:0 0 64px;opacity:.8';
      var i = document.createElement('input'); i.type = 'text'; i.value = val; i.placeholder = ph; i.setAttribute('inputmode', mode || 'text');
      i.autocomplete = 'off'; i.setAttribute('autocapitalize', 'none'); i.spellcheck = false;
      i.style.cssText = 'flex:1;min-width:0;padding:9px 10px;border-radius:10px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.07);color:inherit;font-size:15px';
      i.addEventListener('input', function(){ lsSet(key, i.value.trim()); });
      l.appendChild(t); l.appendChild(i); return l;
    }
    sheet.appendChild(field('PC IP', 'remote13_gp_ip', '192.168.1.20', c.ip, 'decimal'));
    sheet.appendChild(field('Port', 'remote13_gp_port', '8765', c.port, 'numeric'));
    sheet.appendChild(field('PIN', 'remote13_gp_pin', '(khali chhod sakte ho)', c.pin, 'numeric'));
    sheet.appendChild(sbtn(WF.state === 'connected' ? 'Dobara connect karo' : 'Connect', '', WF.state === 'connected' ? 'on' : '', function(){ wfClose(); WF.want = true; wfConnect(); }));
    if(WF.state === 'connected') sheet.appendChild(sbtn('Disconnect', '', 'forget', function(){ wfClose(); refresh(); }));
    sheet.appendChild(sh('CONNECT NAHI HO RAHA?'));
    var ol = document.createElement('ol');
    ['PC par: pip install vgamepad (Windows) phir python gamepad_server.py. Linux par sudo python3 gamepad_server.py.',
     'Phone aur PC ek hi WiFi par ho (guest WiFi / hotspot isolation ho to nahi chalega).',
     'Windows Firewall puche to Allow karo (Private network), ya port 8765 TCP allow karo.',
     'Game me controller XInput / Xbox 360 hona chahiye. Emulator me Controller = Xbox 360 chuno.'].forEach(function(t){ var li = document.createElement('li'); li.textContent = t; ol.appendChild(li); });
    sheet.appendChild(ol);
    sheet.classList.add('open');
  }
'''
rep("  function send(){\n    recompute(); out();", WF + "  function send(){\n    recompute(); out();")

# out(): wifi
rep("    if(tvMode){ tvSend(); return; }\n    if(HID){ try{ HID.pad(",
    "    if(tvMode){ tvSend(); return; }\n    if(wifiMode){ wfSend(); return; }\n    if(HID){ try{ HID.pad(")

# status text
rep("    if(tvMode){ stat.textContent = 'TV keys mode: Google TV se jude remote ke through (Bluetooth nahi chahiye)'; stat.classList.remove('ok'); return; }",
    "    if(tvMode){ stat.textContent = 'TV keys mode: Google TV se jude remote ke through (Bluetooth nahi chahiye)'; stat.classList.remove('ok'); return; }\n"
    "    if(wifiMode){\n"
    "      var c = wfCfg(), t2 = '';\n"
    "      if(WF.state === 'connected') t2 = 'WiFi: PC se connected (' + c.ip + ')' + (WF.player ? ' · Player ' + WF.player : '');\n"
    "      else if(WF.state === 'connecting') t2 = 'WiFi: ' + c.ip + ' se connect ho raha hai…';\n"
    "      else if(WF.state === 'noip') t2 = 'WiFi: yahan tap karke PC ka IP daalo';\n"
    "      else if(WF.state === 'error') t2 = 'WiFi: ' + (WF.err === 'lost' ? 'connection toota' : WF.err === 'timeout' ? 'PC jawab nahi de raha' : 'connect nahi hua') + ' — dobara try kar raha hoon (tap = settings)';\n"
    "      else t2 = 'WiFi: tap karke PC ka IP daalo';\n"
    "      stat.textContent = t2; stat.classList.toggle('ok', WF.state === 'connected'); return;\n"
    "    }")

# stat click
rep("    if(tvMode){ return; }\n    if(sheet.classList.contains('open')){ closeSheet(); return; }\n    if(HID && st !== 'connected'){ try{ HID.reconnect(); }catch(e){} }\n    btSheet();",
    "    if(tvMode){ return; }\n    if(sheet.classList.contains('open')){ closeSheet(); return; }\n    if(wifiMode){ wifiSheet(); return; }\n    if(HID && st !== 'connected'){ try{ HID.reconnect(); }catch(e){} }\n    btSheet();")

# chip + cycling
rep("  function applyModeChip(){ modeBtn.textContent = tvMode ? 'TV keys' : 'BT'; modeBtn.classList.toggle('tv', tvMode); refresh(); }",
    "  function applyModeChip(){ modeBtn.textContent = tvMode ? 'TV keys' : (wifiMode ? 'WiFi' : 'BT'); modeBtn.classList.toggle('tv', tvMode || wifiMode); refresh(); }")
rep("    releaseAll(); tvMode = !tvMode; lsSet('remote13_gp_mode', tvMode ? 'tv' : 'bt'); closeSheet(); applyModeChip();",
    "    releaseAll(); wfClose();\n"
    "    gpMode = gpMode === 'bt' ? 'wifi' : (gpMode === 'wifi' ? 'tv' : 'bt');          // BT -> WiFi (PC) -> TV keys -> BT\n"
    "    tvMode = gpMode === 'tv'; wifiMode = gpMode === 'wifi'; lsSet('remote13_gp_mode', gpMode); closeSheet(); applyModeChip();\n"
    "    if(wifiMode){ if(!wfCfg().ip){ WF.state = 'noip'; refresh(); wifiSheet(); } else wfEnsure(); }\n"
    "    else if(gpMode === 'bt' && HID){ try{ HID.start(); }catch(e){} }")
rep("    if(!tvMode){\n      if(!HID){ stat.textContent = 'Game pad sirf app me chalta hai'; return; }",
    "    if(wifiMode){ if(!wfCfg().ip){ WF.state = 'noip'; refresh(); setTimeout(wifiSheet, 300); } else wfEnsure(); return; }\n    if(!tvMode){\n      if(!HID){ stat.textContent = 'Game pad sirf app me chalta hai'; return; }")
rep("    releaseAll(); closeSheet();\n    ov.classList.remove('show');","    releaseAll(); closeSheet(); wfClose();\n    ov.classList.remove('show');")
rep('title="Bluetooth ya Google TV keys">BT</button>','title="Bluetooth / WiFi (PC) / Google TV keys">BT</button>')
open(p,'w',encoding='utf-8').write(s); print('ok')
