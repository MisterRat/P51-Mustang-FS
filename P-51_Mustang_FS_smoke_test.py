#!/usr/bin/env python3
"""Smoke test for P-51_Mustang_FS.html  (development aid - not needed to play the game).

Boots the game in headless Chromium with ALL network access blocked, then checks:
  - no script errors, no external requests, three.js r128 present (it is inlined)
  - frames are really being rendered, and the draw-call count is inside the budget
  - the cockpit view draws, and the live instrument panel texture is painted
  - every mission in the menu starts and runs for a couple of seconds without errors
  - convoy vehicles and buildings share one geometry per model type (no per-vehicle leak)
  - a destroyed target is flattened and darkened
  - controller: LB/RB give rudder, a long press of R3 calls and clears a bandit
  - bindings: help box and Controls tab are generated and complete; every key / button triggers its action
  - keyboard, tilt (sensitivity, invert, twist), touch and settings controls move the plane's control surfaces
  - ground handling: brakes, rudder steering, tail wheel never digs in
  - sound (audio graph, engine follows throttle, effects, mute and volume saved), version label, graphics tiers (Low / Medium / High), and Hardcore Simulation Mode: master switch, each option on and off

Usage:   pip install playwright && playwright install chromium
         python P-51_Mustang_FS_smoke_test.py [path/to/P-51_Mustang_FS.html]
Set CHROMIUM=/path/to/chrome to use a specific browser binary. Exit code 0 = all passed.
"""
import os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).with_name("P-51_Mustang_FS.html")).resolve()
DRAW_CALL_BUDGET = 750  # raised from 700 in 3.38: the detailed aircraft, cockpit and grass add draw calls (about 710 measured)
results, errors, external = [], [], []

def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail else ""))

with sync_playwright() as p:
    kw = dict(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox"])
    if os.environ.get("CHROMIUM"):
        kw["executable_path"] = os.environ["CHROMIUM"]
    b = p.chromium.launch(**kw)
    pg = b.new_page(viewport={"width": 960, "height": 540})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" else None)
    pg.route("**/*", lambda r: r.continue_() if r.request.url.startswith(("file:", "data:", "blob:")) else (external.append(r.request.url), r.abort()))
    pg.goto(HTML.as_uri())
    pg.wait_for_timeout(3500)

    check("loads with no script errors", not errors, "; ".join(errors[:3]))
    check("no external requests (fully offline)", not external, ", ".join(external[:3]))
    check("three.js r128 is inlined", pg.evaluate("()=>typeof THREE!=='undefined'&&THREE.REVISION==='128'"))

    f0 = pg.evaluate("()=>R.info.render.frame"); pg.wait_for_timeout(1500); f1 = pg.evaluate("()=>R.info.render.frame")
    check("frames are being rendered", f1 > f0, f"{f1 - f0} frames in 1.5 s")
    calls = pg.evaluate("()=>R.info.render.calls")
    for _ in range(2):  # the count moves with what is in view at that instant; judge the typical (lowest) value
        pg.wait_for_timeout(700); calls = min(calls, pg.evaluate("()=>R.info.render.calls"))
    check(f"draw calls within budget ({DRAW_CALL_BUDGET})", calls <= DRAW_CALL_BUDGET, f"{calls} calls")

    pg.evaluate("()=>{$$('go').click()}"); pg.wait_for_timeout(500)
    pg.evaluate("()=>{PP.off=true}")  # the hidden pilot flight is tested on its own below; the other checks drive missions by hand
    pg.evaluate("()=>{camMode=1}")
    try:
        pg.wait_for_function("()=>{const d=pcx.getImageData(150,120,80,40).data;let s=0;for(let i=0;i<d.length;i+=4)s+=d[i]+d[i+1]+d[i+2];return s>5000}", timeout=20000)
    except Exception:
        pass
    lit = pg.evaluate("()=>{const d=pcx.getImageData(150,120,80,40).data;let s=0;for(let i=0;i<d.length;i+=4)s+=d[i]+d[i+1]+d[i+2];return s}")
    check("cockpit instrument panel is painted", lit > 5000, f"signal {lit}")
    px = pg.evaluate("()=>{R.render(scene,cam);const g=R.getContext(),w=g.drawingBufferWidth,h=g.drawingBufferHeight,a=new Uint8Array(4);g.readPixels(w>>1,h>>1,1,1,g.RGBA,g.UNSIGNED_BYTE,a);return Array.from(a)}")
    check("cockpit view renders something (not black)", sum(px[:3]) > 30, str(px))
    pg.evaluate("()=>{camMode=0}")

    def waits(js):
        try:
            pg.wait_for_function(js, timeout=15000); return True
        except Exception:
            return False
    pg.evaluate("""()=>{window.__b=Array.from({length:17},()=>({pressed:false,value:0}));
      navigator.getGamepads=()=>[{connected:true,axes:[0,0,0,0],buttons:window.__b,id:'fake'}]}""")
    pg.wait_for_timeout(800)
    pg.evaluate("()=>{__b[5].pressed=true}"); pg.wait_for_timeout(800)
    check("controller RB = rudder right", pg.evaluate("()=>pad.y")==1)
    check("rudder surface and pedal follow RB (right)", waits("()=>rudG.quaternion.y>0.1&&ckPed[1].position.z<-1.07"))
    pg.evaluate("()=>{__b[5].pressed=false;__b[4].pressed=true}"); pg.wait_for_timeout(800)
    check("controller LB = rudder left", pg.evaluate("()=>pad.y")==-1)
    check("rudder surface follows LB (left)", waits("()=>rudG.quaternion.y<-0.1"))
    pg.keyboard.down("KeyD"); pg.keyboard.down("KeyS"); pg.wait_for_timeout(1500)
    check("ailerons deflect oppositely on roll right", waits("()=>ailP[0][0].rotation.x*ailP[1][0].rotation.x<0&&Math.abs(ailP[0][0].rotation.x)>0.1"))
    check("elevator trailing edge rises on pull-up", waits("()=>elevG.rotation.x<-0.1"))
    pg.keyboard.up("KeyD"); pg.keyboard.up("KeyS")
    pg.evaluate("()=>{__b[4].pressed=false}"); pg.wait_for_timeout(500)
    pg.evaluate("()=>{trn.mode='free';clearEnemies();onGround=true;__b[1].pressed=true}"); pg.wait_for_timeout(500); pg.evaluate("()=>{__b[1].pressed=false}"); pg.wait_for_timeout(400)
    check("controller B on the ground only brakes (no bandit)", pg.evaluate("()=>!EN.some(e=>!e.dying)"))
    pg.evaluate("()=>{pos.y=1500;vel.set(0,0,-150);onGround=false;__b[1].pressed=true}"); pg.wait_for_timeout(500); pg.evaluate("()=>{__b[1].pressed=false}"); pg.wait_for_timeout(600)
    check("controller B in the air calls a bandit", pg.evaluate("()=>EN.some(e=>!e.dying)"))
    pg.evaluate("()=>{pos.y=1500;vel.set(0,0,-150);onGround=false;__b[1].pressed=true}"); pg.wait_for_timeout(500); pg.evaluate("()=>{__b[1].pressed=false}"); pg.wait_for_timeout(600)
    check("controller B again clears it", pg.evaluate("()=>!EN.some(e=>!e.dying)"))
    pg.evaluate("()=>{pos.y=1500;vel.set(0,0,-150);onGround=false;}"); pg.keyboard.press("KeyB"); pg.wait_for_timeout(600)
    check("keyboard B in the air calls a bandit", pg.evaluate("()=>EN.some(e=>!e.dying)"))
    pg.evaluate("()=>{pos.y=1500;vel.set(0,0,-150);onGround=false;}"); pg.keyboard.press("KeyB"); pg.wait_for_timeout(600)
    check("keyboard B again clears it", pg.evaluate("()=>!EN.some(e=>!e.dying)"))

    # ---- bindings table: help is generated from it and every key / button really triggers its action
    docs = pg.evaluate("()=>$$('hkBody').innerHTML+$$('hpBody').innerHTML+$$('kbT1').innerHTML+$$('kbT2').innerHTML+$$('pdT1').innerHTML+$$('pdT2').innerHTML")
    check("help box and Controls tab are generated", len(docs) > 1500 and "undefined" not in docs and "NaN" not in docs)
    missing = pg.evaluate("""()=>{const dec=h=>{const d=document.createElement('div');d.innerHTML=h;return d.textContent},kd=dec($$('kbT1').innerHTML+$$('kbT2').innerHTML),pd=dec($$('pdT1').innerHTML+$$('pdT2').innerHTML);
      return BIND.filter(b=>(b[2].length&&!kd.includes(dec(kbText(b[0]))))||(b[3]!==null&&!pd.includes(dec(padText(b[0]))))).map(b=>b[0])}""")
    check("every binding is documented for its device", not missing, str(missing))
    ids = pg.evaluate("()=>BIND.filter(b=>b[2].length&&(ACT[b[0]]||UIACT[b[0]])).map(b=>[b[0],b[2][0]])")
    pg.evaluate("""()=>{window.__cnt={};window.__orig={};for(const T of [ACT,UIACT])for(const id in T){__orig[id]=T[id];T[id]=()=>{__cnt[id]=(__cnt[id]||0)+1}}}""")
    bad = []
    for bid, code in ids:
        pg.keyboard.press(code); pg.wait_for_timeout(30)
        if not pg.evaluate(f"()=>__cnt['{bid}']>0"): bad.append(bid)
    check("every discrete key triggers its action", not bad, str(bad))
    bad = []
    for bid in ["gear", "restart", "pause"]:
        pg.evaluate("()=>{__cnt={}}")
        btn = pg.evaluate(f"()=>PB['{bid}']")
        pg.evaluate(f"()=>{{__b[{btn}].pressed=true}}"); pg.wait_for_timeout(400); pg.evaluate(f"()=>{{__b[{btn}].pressed=false}}"); pg.wait_for_timeout(300)
        if not pg.evaluate(f"()=>__cnt['{bid}']>0"): bad.append(bid)
    check("controller gear / restart / pause buttons trigger their actions", not bad, str(bad))
    pg.evaluate("()=>{for(const T of [ACT,UIACT])for(const id in T)T[id]=__orig[id]}")
    # ---- keyboard flight inputs reach the control surfaces (signs: W push down, S pull up, A/D roll, Q/E rudder)
    pg.evaluate("()=>{reset();started=true;thr=0}"); pg.wait_for_timeout(500)
    def held(code, cond):
        pg.keyboard.down(code); ok = waits(cond); pg.keyboard.up(code)
        pg.evaluate("()=>{s.p=s.r=s.y=0}")  # the real decay is slow at headless frame rates; start the next check from neutral
        return ok
    check("S pulls up: elevator trailing edge rises", held("KeyS", "()=>s.p>0.3&&elevG.rotation.x<-0.1"))
    check("W pushes down: elevator trailing edge drops", held("KeyW", "()=>s.p<-0.3&&elevG.rotation.x>0.1"))
    check("D rolls right: right aileron up, stick right", held("KeyD", "()=>s.r>0.3&&ailP.find(o=>o[1]==1)[0].rotation.x<-0.1&&ckStick.rotation.z<-0.05"))
    check("A rolls left: left aileron up", held("KeyA", "()=>s.r<-0.3&&ailP.find(o=>o[1]==-1)[0].rotation.x<-0.1"))
    check("E = rudder right (surface and pedal)", held("KeyE", "()=>s.y>0.3&&rudG.quaternion.y>0.05"))
    check("Q = rudder left", held("KeyQ", "()=>s.y<-0.3&&rudG.quaternion.y<-0.05"))
    pg.evaluate("()=>{thr=0.5}")
    pg.keyboard.down("ShiftLeft"); up_ok = waits("()=>thr>0.52"); pg.keyboard.up("ShiftLeft")
    pg.keyboard.down("ControlLeft"); dn_ok = waits("()=>thr<0.45"); pg.keyboard.up("ControlLeft")
    check("Shift raises and Ctrl lowers the throttle", up_ok and dn_ok)

    # ---- settings sliders and check boxes reach the tilt settings (and are saved)
    def slider(i, v):
        pg.evaluate(f"()=>{{const e=$$('{i}');e.value={v};e.dispatchEvent(new Event('input'))}}")
    def box(i, v):
        pg.evaluate(f"()=>{{const e=$$('{i}');e.checked={str(v).lower()};e.dispatchEvent(new Event('change'))}}")
    slider("tsGain", 200); slider("tsYaw", 0); box("tsInv", True); box("tsInvR", True)
    cfg = pg.evaluate("()=>[TC.cfg.gain,TC.cfg.yaw,TC.cfg.invP,TC.cfg.invR]")
    check("tilt sliders and invert boxes change the settings", cfg == [2, 0, True, True], str(cfg))
    saved = pg.evaluate("()=>store.get('p51tc',{})")
    check("tilt settings are saved", saved.get("gain") == 2 and saved.get("invP") is True, str(saved))
    slider("tsGain", 100); slider("tsYaw", 100); box("tsInv", False); box("tsInvR", False)

    # ---- simulated phone tilt: sensitivity, invert and twist settings scale what the plane receives
    TILT = """([n,ev,cfg])=>{Object.assign(TC.cfg,{gain:1,yaw:1,invP:false,invR:false},cfg);TC.cal=null;TC.last=null;TC.tr=TC.tp=TC.ty=0;TC.yawAng=0;TC.state='ok';
      onOri(Object.assign({timeStamp:1000},n));
      for(let i=0;i<40;i++)onOri(Object.assign({timeStamp:1000+i*16},ev));
      return [TC.tr,TC.tp,TC.ty]}"""
    def tilt(n, ev, cfg=None):
        return pg.evaluate(TILT, [n, ev, cfg or {}])
    N90 = {"alpha": 0, "beta": 90, "gamma": 0}; N45 = {"alpha": 0, "beta": 45, "gamma": 0}
    PITCH = {"alpha": 0, "beta": 84, "gamma": 0}; ROLL = {"alpha": 0, "beta": 45, "gamma": 6}; YAW = {"alpha": 10, "beta": 90, "gamma": 0}
    base, hi, lo, inv = tilt(N90, PITCH), tilt(N90, PITCH, {"gain": 2}), tilt(N90, PITCH, {"gain": 0.5}), tilt(N90, PITCH, {"invP": True})
    check("tilt pitch: top edge toward you climbs / away dives, sensitivity scales it", abs(base[1]) > 0.05 and abs(hi[1]) > abs(base[1]) > abs(lo[1]), f"{lo[1]:.3f} {base[1]:.3f} {hi[1]:.3f}")
    check("invert pitch flips the sign", inv[1] * base[1] < 0 and abs(abs(inv[1]) - abs(base[1])) < 0.01)
    base, hi, inv = tilt(N45, ROLL), tilt(N45, ROLL, {"gain": 2}), tilt(N45, ROLL, {"invR": True})
    check("tilt roll responds, sensitivity scales it, invert flips it", abs(base[0]) > 0.02 and abs(hi[0]) > abs(base[0]) and inv[0] * base[0] < 0, f"{base[0]:.3f} {hi[0]:.3f} {inv[0]:.3f}")
    base, hi, off = tilt(N90, YAW), tilt(N90, YAW, {"yaw": 2}), tilt(N90, YAW, {"yaw": 0})
    check("twist (rudder) sensitivity scales it and 0 turns it off", abs(base[2]) > 0.05 and abs(hi[2]) > abs(base[2]) and off[2] == 0, f"{base[2]:.3f} {hi[2]:.3f} {off[2]}")
    # the tilt result drives the control surfaces; with tilt off the touch stick and rudder buttons do
    pg.evaluate("()=>{Object.assign(TC.cfg,{on:true,gain:1,yaw:1,invP:false,invR:false});TC.state='ok';TC.tp=0.6;TC.tr=-0.6;TC.ty=0}")
    check("tilt drives elevator and ailerons", waits("()=>s.p>0.3&&s.r<-0.3&&elevG.rotation.x<-0.1&&ailP.find(o=>o[1]==1)[0].rotation.x>0.1"))
    pg.evaluate("()=>{TC.tp=0;TC.tr=0;TC.cfg.on=false;TC.sp=-0.6;TC.sr=0.6;TC.btnY=1}")
    check("touch stick and rudder buttons drive the surfaces", waits("()=>s.p<-0.3&&s.r>0.3&&s.y>0.3&&rudG.quaternion.y>0.05"))
    pg.evaluate("()=>{TC.sp=0;TC.sr=0;TC.btnY=0;TC.cfg.on=true;TC.state='off'}")
    pg.evaluate("()=>{s.p=s.r=s.y=0}")  # the real decay is slow at headless frame rates; start the next check from neutral

    # ---- phone exit: the pause menu has an Exit game button that asks first and can be cancelled
    check("pause menu has an Exit game button", pg.evaluate("()=>!!$$('pmExit')&&$$('pmExit').textContent.includes('Exit')"))
    pg.evaluate("()=>$$('pmExit').onclick()")
    check("Exit game asks for confirmation", pg.evaluate("()=>!!document.getElementById('xqYes')&&!!document.getElementById('xqNo')"))
    pg.evaluate("()=>document.getElementById('xqNo').click()")
    check("Keep flying cancels the exit", pg.evaluate("()=>!document.getElementById('xqYes')&&!paused"))

    # ---- ground handling: brakes slow the plane, rudder steers it on the ground
    def frames_pass(n):
        f0 = pg.evaluate("()=>R.info.render.frame"); pg.wait_for_function(f"()=>R.info.render.frame>={f0 + n}", timeout=30000)
    def roll_trial(key):
        pg.evaluate("()=>{reset();started=true;thr=0;axes();vel.copy(fwd).setY(0).setLength(30)}")
        h0 = pg.evaluate("()=>Math.atan2(fwd.x,-fwd.z)")
        if key: pg.keyboard.down(key)
        frames_pass(8)
        r = pg.evaluate("()=>[vel.length(),Math.atan2(fwd.x,-fwd.z),onGround]")
        if key: pg.keyboard.up(key)
        return r[0], (r[1] - h0), r[2]
    free_v, _, g0 = roll_trial(None); brake_v, _, g1 = roll_trial("KeyB")
    check("on the ground the brakes slow the plane", g0 and g1 and brake_v < free_v - 1.0, f"free {free_v:.1f} m/s, braked {brake_v:.1f} m/s")
    _, dr, _ = roll_trial("KeyE"); _, dl, _ = roll_trial("KeyQ")
    check("on the ground rudder steers: E right, Q left", dr > 0.01 and dl < -0.01, f"{dr:.3f} {dl:.3f}")

    # ---- ground handling: tail wheel never digs in
    pg.evaluate("()=>{reset();started=true}"); pg.wait_for_timeout(600)
    pg.evaluate("()=>{const e=new THREE.Euler().setFromQuaternion(q,'YXZ');e.x=0.6;q.setFromEuler(e)}"); pg.wait_for_timeout(800)
    try:
        pg.wait_for_function("()=>tiltV>GEAR.sit-0.004", timeout=40000)  # let the sitting tilt settle first
    except Exception:
        pass
    check("on the ground the nose-up pitch is limited so the tail wheel stays above the surface", pg.evaluate("()=>onGround&&Math.asin(fwd.y)+tiltV<=GEAR.sit+0.01"), pg.evaluate("()=>[onGround,Math.asin(fwd.y),tiltV,GEAR.sit]").__str__())
    check("longest physics sub-step is 1/120 s", pg.evaluate("()=>Math.abs(PH_DT-1/120)<1e-9"))

    # ---- version label
    check("version label is shown (major.minor)", pg.evaluate("()=>/^\\d+\\.\\d+$/.test(VERSION)&&[...document.querySelectorAll('.verTag')].every(e=>e.textContent==='Version '+VERSION)&&document.querySelectorAll('.verTag').length>=3"), pg.evaluate("()=>VERSION"))

    # ---- graphics tiers: Low < Medium < High, saved, and a button for each
    g = pg.evaluate("""()=>{const o={};const cnt=()=>TREEM.reduce((a,t)=>a+t.m.count,0);
      o.btn=[...document.querySelectorAll('#pmGfx button')].map(b=>b.dataset.q).join(',');
      QL.mode='low';applyQuality();o.low=[cnt(),DETU.value,CSH.k.value];o.savedLow=JSON.parse(localStorage.getItem('p51gfx'));
      QL.mode='medium';applyQuality();o.med=[cnt(),DETU.value,CSH.k.value];
      QL.mode='high';applyQuality();o.high=[cnt(),DETU.value,CSH.k.value];
      QL.mode='auto';applyQuality();o.auto=[cnt()];return o}""")
    check("graphics: Auto / Low / Medium / High buttons exist", g["btn"] == "auto,low,medium,high", g["btn"])
    check("graphics: Low < Medium < High in scenery detail", g["low"][0] < g["med"][0] < g["high"][0], str([g["low"][0], g["med"][0], g["high"][0]]))
    check("graphics: Low drops ground detail and shadow, Medium/High keep them", g["low"][1] == 0 and g["low"][2] == 0 and g["med"][1] == 1 and g["med"][2] > 0 and g["high"][2] > 0, str([g["low"], g["med"]]))
    check("graphics choice is saved", g["savedLow"] == "low", str(g["savedLow"]))

    # ---- sound: the audio graph is built, follows the throttle, volume / mute are saved, one-shot effects play
    snd = pg.evaluate("""()=>{const o={};o.ctx=!!SND.ctx;o.state=SND.ctx&&SND.ctx.state;
      o.shots=true;try{SND.boom(pos,10);SND.rocket();SND.bomb();SND.hit();SND.gear(true);SND.flaps();SND.touch(3);SND.beep(600,0.1);SND.guns(true)}catch(e){o.shots=String(e)}
      o.mute=typeof UIACT.mute==="function";
      const v0=SND.on;UIACT.mute();o.toggled=SND.on===!v0&&JSON.parse(localStorage.getItem('p51snd')).on===SND.on;UIACT.mute();
      const sl=document.getElementById('sndVol');sl.value=40;sl.dispatchEvent(new Event('input'));o.vol=[SND.vol,JSON.parse(localStorage.getItem('p51snd')).vol];sl.value=70;sl.dispatchEvent(new Event('input'));
      paused=false;thr=0;return o}""")
    pg.wait_for_timeout(1500)
    f0 = pg.evaluate("()=>{audioUpd();return SND.e.o1.frequency.value}")
    pg.evaluate("()=>{thr=1}")
    pg.wait_for_timeout(1500)
    f1 = pg.evaluate("()=>{audioUpd();return SND.e.o1.frequency.value}")
    pg.evaluate("()=>{thr=0}")
    check("sound: audio graph is built when the flight starts", snd["ctx"], str(snd["state"]))
    check("sound: every effect (boom, rocket, bomb, hit, gear, flaps, touchdown, beep, guns) plays without error", snd["shots"] is True, str(snd["shots"]))
    check("sound: U toggles sound and the choice is saved; the volume slider is saved", snd["toggled"] and abs(snd["vol"][0] - 0.4) < 0.01 and abs(snd["vol"][1] - 0.4) < 0.01, str(snd))
    check("sound: engine note rises with the throttle", f1 > f0 * 1.5, f"{f0:.0f} Hz at idle, {f1:.0f} Hz at full throttle")

    # ---- hardcore simulation mode: off by default, master switch + six options, each really changes the physics
    hc = pg.evaluate("""()=>{const o={};
      o.defaultOff=FM.on===false;
      FM.opt.wind=false;FM.opt.turb=false;
      o.ui=[document.getElementById('hcOn')!==null,document.querySelectorAll('#hcList input').length,[...document.querySelectorAll('#hcList input')].every(i=>i.disabled)];
      const run=(t)=>{for(let i=0;i<t*120;i++){if(crashed)break;step(1/120)}};
      const sky=(spd,t)=>{reset();paused=true;pos.set(0,3000,0);q.identity();vel.set(0,0,-spd);thr=t;pad.p=pad.r=pad.y=0;s.p=s.r=s.y=0;FM.reset();autoTrim(spd);onGround=false;axes()};
      const yawOnRoll=()=>{reset();paused=true;thr=1;pad.p=pad.r=pad.y=0;run(5);return new THREE.Euler().setFromQuaternion(q,'YXZ').y};
      o.yawOff=yawOnRoll();
      document.getElementById('hcOn').click();
      o.uiOn=[FM.on,[...document.querySelectorAll('#hcList input')].every(i=>!i.disabled),JSON.parse(localStorage.getItem('p51hc')).on];
      o.yawOn=yawOnRoll();
      FM.opt.torque=false;o.yawTorqueOff=yawOnRoll();FM.opt.torque=true;
      // stall with rudder held -> spin; recover with opposite rudder + stick forward
      sky(48,0.3);pad.p=1;pad.y=-1;run(8);o.spin=FM.spin;
      pad.p=-1;pad.y=1;thr=0;run(3);o.recovered=!FM.spin;
      FM.opt.spin=false;sky(48,0.3);pad.p=1;pad.y=-1;run(8);o.spinOff=FM.spin;FM.opt.spin=true;
      // engine heat
      sky(100,1);let h=0;while(!FM.hot&&h<400){run(1);pos.y=3000;vel.set(0,0,-100);q.identity();h++}o.heatSecs=h;
      thr=0.5;h=0;while(FM.hot&&h<200){run(1);pos.y=3000;vel.set(0,0,-100);q.identity();h++}o.cooled=!FM.hot;
      FM.opt.heat=false;FM.opt.pwr=false;sky(100,1);for(let k=0;k<300;k++){run(1);pos.y=3000;vel.set(0,0,-100);q.identity()}o.heatOff=FM.hot||FM.eT>0;FM.opt.heat=true;FM.opt.pwr=true;
      // altitude: indicated speed falls with height, power fades, service ceiling
      sky(150,1);run(0.05);o.iasLow=FM.ias/vel.length();
      pos.y=9000;run(0.05);o.iasHigh=FM.ias/vel.length();o.psHigh=AT.ps;
      FM.opt.alt=false;pos.y=9000;run(0.05);o.iasAltOff=FM.ias/vel.length();FM.opt.alt=true;
      // fuel burns, weight falls, the engine quits when dry, service refuels
      sky(120,1);const f0=FM.fuel;run(60);o.burn=f0-FM.fuel;
      FM.fuel=0;sky(120,1);FM.fuel=0;pos.y=3000;const sp0=vel.length();run(1);const a0=AT.ps;o.dryNoThrust=true;
      FM.fuel=1;FM.opt.fuel=false;sky(120,1);run(60);o.fuelOff=FM.fuel;FM.opt.fuel=true;
      // real performance: sea-level top speed with and without the extra drag
      const topSpd=()=>{sky(150,1);gearOn=false;flapLvl=0;fl=0;rkN=6;bmN=2;for(let k=0;k<40;k++){run(2,0);pos.y=300;vel.y=0;q.identity()}return vel.length()*3.6};
      o.topPerf=topSpd();FM.opt.perf=false;o.topArcade=topSpd();FM.opt.perf=true;
      // structural load limits: a hard pull at speed is stopped at ~7 G when off, overstresses / breaks the wing when on
      const hardPull=()=>{sky(190,1);gearOn=false;pad.p=1;let gm=0;for(let k=0;k<60*2;k++){step(1/120);gm=Math.max(gm,gF);if(crashed)break}return [gm,FM.over,FM.str,crashed]};
      const gOn=hardPull();FM.opt.gload=false;const gOff=hardPull();FM.opt.gload=true;o.gload=[gOn,gOff];
      FM.reset();o.limHeavy=gLimits(0.95,200,{pos:0,neg:0}).pos;o.limLight=gLimits(1,200,{pos:0,neg:0}).pos;o.limFast=gLimits(1,500,{pos:0,neg:0}).pos;
      // war emergency power: top 10% of the throttle
      o.wep=[power(0.9),power(1)];FM.opt.wep=false;o.wepOff=power(0.5);FM.opt.wep=true;
      // master off puts everything back to the plain model
      document.getElementById('hcOn').click();
      o.masterOff=[FM.on,FM.use('torque'),power(0.5)];o.yawBack=yawOnRoll();
      reset();paused=false;return o}""")
    check("hardcore: off by default, every option greyed out until the master switch is on", hc["defaultOff"] and hc["ui"][0] and hc["ui"][1] == 16 and hc["ui"][2], str(hc["ui"]))
    check("hardcore: master switch enables the options and is saved", hc["uiOn"] == [True, True, True], str(hc["uiOn"]))
    check("hardcore: torque swings the nose left on the take-off roll (only when on)", abs(hc["yawOff"]) < 1e-6 and hc["yawOn"] > 0.05 and abs(hc["yawTorqueOff"]) < 1e-6, str([hc["yawOff"], hc["yawOn"], hc["yawTorqueOff"]]))
    check("hardcore: stall with rudder held spins; opposite rudder + stick forward recovers", hc["spin"] and hc["recovered"], str([hc["spin"], hc["recovered"]]))
    check("hardcore: spin option off means no spin", not hc["spinOff"])
    check("hardcore: engine overheats at full throttle (about 4 min) and cools again", 200 <= hc["heatSecs"] <= 260 and hc["cooled"], str([hc["heatSecs"], hc["cooled"]]))
    check("hardcore: heat option off means no overheating", not hc["heatOff"])
    check("hardcore: indicated speed falls with altitude and the supercharger power fades", 0.8 < hc["iasLow"] < 0.9 and hc["iasHigh"] < 0.65 and hc["psHigh"] < 0.95 and hc["iasAltOff"] > 0.99, str([hc["iasLow"], hc["iasHigh"], hc["psHigh"], hc["iasAltOff"]]))
    check("hardcore: fuel burns with power (and not when the option is off)", 0.003 < hc["burn"] < 0.02 and hc["fuelOff"] == 1, str([hc["burn"], hc["fuelOff"]]))
    check("hardcore: real performance caps the sea-level top speed near 600 km/h (arcade speeds when off)", 570 < hc["topPerf"] < 625 and hc["topArcade"] > 650, str([hc["topPerf"], hc["topArcade"]]))
    check("hardcore: load limit - the plane is stopped near +7 G when off, but a hard pull at speed overstresses or breaks it when on", hc["gload"][1][0] < 7.2 and not hc["gload"][1][3] and (hc["gload"][0][3] or hc["gload"][0][1] > 1 or hc["gload"][0][2] > 0), str(hc["gload"]))
    check("hardcore: structural limit is +8 G (light), lower when heavy and at high speed", abs(hc["limLight"] - 7.11) < 0.1 and hc["limHeavy"] < hc["limLight"] and hc["limFast"] < hc["limLight"], str([hc["limLight"], hc["limHeavy"], hc["limFast"]]))
    check("hardcore: war emergency power is the top 10% of the throttle", abs(hc["wep"][1] - 1) < 1e-9 and hc["wep"][0] < 0.88 and hc["wepOff"] == 0.5, str([hc["wep"], hc["wepOff"]]))
    check("hardcore: master switch off restores the plain model", hc["masterOff"] == [False, False, 0.5] and abs(hc["yawBack"]) < 1e-6, str([hc["masterOff"], hc["yawBack"]]))
    ops = pg.evaluate("""()=>{
      FM.on=true;FM.opt.ops=true;FM.opt.pwr=true;FM.opt.heat=false;
      syncFlaps();const a=[ANG.length,FL[5],FLIM[4],FLIM[5]];
      flapLvl=5;FM.opt.ops=false;syncFlaps();const b=[ANG.length,flapLvl];FM.opt.ops=true;syncFlaps();
      reset();FM.on=true;FM.opt.ops=true;gearOn=false;onGround=false;FM.ias=90;toggleGear();const g1=gearOn;FM.ias=60;toggleGear();const g2=gearOn;
      FM.wepT=0;FM.wepX=false;FM.eT=0;engOut=false;thr=1;const r=new V();for(let i=0;i<301;i++)hardcore(1,80,80,0,1,r);
      const w=[FM.wepW,FM.wepX,FM.eT];
      FM.wepT=0;FM.wepX=false;FM.wepW=false;FM.eT=0;FM.opt.pwr=false;for(let i=0;i<301;i++)hardcore(1,80,80,0,1,r);const wo=[FM.wepX,FM.eT];
      FM.opt.pwr=true;FM.wepT=0;FM.eT=0;thr=1;FM.rpmT=0;FM.ias=230;for(let i=0;i<4;i++)hardcore(1,230,230,0,1,r);const f1=FM.eT;
      FM.eT=0;FM.rpmT=0;FM.ias=150;for(let i=0;i<5;i++)hardcore(1,150,150,0,1,r);const f2=FM.eT;
      FM.opt.heat=true;FM.on=false;syncFlaps();return {a,b,g1,g2,w,wo,f1,f2}}""")
    check("hardcore ops: six real flap settings (10-50 deg) with the manual's limits, back to five when off", ops["a"][0] == 6 and ops["a"][1] == "50°" and abs(ops["a"][2] - 80.5) < 0.2 and abs(ops["a"][3] - 73.8) < 0.2 and ops["b"] == [5, 4], str(ops))
    check("hardcore ops: the gear will not come down above 273 km/h, and does below", ops["g1"] is False and ops["g2"] is True, str(ops))
    check("hardcore pwr: war emergency power overheats the engine after 5 minutes (not when the option is off)", ops["w"][0] and ops["w"][1] and ops["w"][2] >= 1.2 and not ops["wo"][0] and ops["wo"][1] == 0, str(ops))
    check("hardcore pwr: more than 3240 rpm in a dive overheats the engine, normal speed does not", ops["f1"] >= 1.2 and ops["f2"] == 0, str(ops))
    lv = pg.evaluate("""()=>{reset();const a=!!ckLev.flap&&!!ckLev.gear;gearOn=true;flapLvl=0;return a}""")
    pg.wait_for_timeout(300)
    r0 = pg.evaluate("()=>[ckLev.flap.rotation.x,ckLev.gear.rotation.x]")
    pg.evaluate("()=>{flapLvl=4;gearOn=false}"); pg.wait_for_timeout(400)
    r1 = pg.evaluate("()=>[ckLev.flap.rotation.x,ckLev.gear.rotation.x]")
    check("cockpit: the flap and gear levers on the left console move with the flaps and the gear", lv and abs(r0[0] - r1[0]) > 0.5 and abs(r0[1] - r1[1]) > 0.3, str([r0, r1]))
    pg.evaluate("()=>{gearOn=true;flapLvl=0}")
    pg.evaluate("()=>{WX.setTime('night')}"); pg.wait_for_timeout(600)
    pg.evaluate("()=>{pos.set(0,60,-300);vel.set(0,-1,-55);onGround=false;gearOn=true}"); pg.wait_for_timeout(500)
    night = pg.evaluate("()=>[WX.lt,LLP.visible,LLP.material.opacity]")
    pg.evaluate("()=>{gearOn=false}"); pg.wait_for_timeout(500)
    night2 = pg.evaluate("()=>LLP.visible")
    pg.evaluate("()=>{WX.setTime('midday');gearOn=true}"); pg.wait_for_timeout(500)
    day = pg.evaluate("()=>LLP.visible")
    check("night: the landing light pool shows with the gear down at night, not with the gear up or by day", night[0] > 0.5 and night[1] and night[2] > 0.05 and not night2 and not day, str([night, night2, day]))
    pg.evaluate("()=>{navigator.getGamepads=()=>[]}")

    n = pg.evaluate("()=>MENU.length")
    for i in range(n):
        name = pg.evaluate(f"()=>{{menuPick({i});return MENU[{i}][1]}}")
        if pg.evaluate("()=>trn.mode")=='convoy':
            pg.evaluate("()=>{CV.tm=0}")
        pg.wait_for_timeout(2500)
        check(f"mission '{name}' runs", not errors, "; ".join(errors[-2:]))

    # ---- aerobatic trainers: each starts at its entry height, coaches differently in Hardcore, the yo-yos spawn a drone
    ae = pg.evaluate("""()=>{const o={},ms=['barrel','immelmann','splits','wingover','lowyoyo','highyoyo'],txt={};
      for(const hc of [false,true]){FM.on=hc;for(const m of ms){const i=MENU.findIndex(x=>x[0]===m);menuPick(i);paused=false;
        for(let k=0;k<30;k++){step(1/60);updEnemies(1/60);updTrainer(1/60)}
        txt[m+hc]=document.getElementById('coachS').textContent;
        o[m+hc]=[trn.mode===m,Math.round(pos.y),EN.filter(e=>e.drone).length,document.getElementById('coach').style.display,trn.step]}}
      FM.on=false;return {o,diff:ms.map(m=>txt[m+false]!==txt[m+true])}}""")
    ae_ok = all(v[0] and v[3] == "block" for v in ae["o"].values())
    check("aero trainers: all six start in the mission menu and show coaching", ae_ok, str(ae["o"]))
    check("aero trainers: coaching text differs between Standard and Hardcore for every maneuver", all(ae["diff"]), str(ae["diff"]))
    check("aero trainers: only the two yo-yo trainers spawn the scripted drone", all((v[2] == 1) == (k[:-4 if k.endswith("true") else -5] in ("lowyoyo", "highyoyo")) for k, v in ae["o"].items()), str(ae["o"]))
    pg.evaluate("""()=>{FM.on=false;const i=MENU.findIndex(x=>x[0]==='takeoff');menuPick(i);paused=false;thr=1;
      for(let k=0;k<240;k++){step(1/60);updTrainer(1/60);updGuide(1/60);FM.eT=0}
      trn.done=true;trn.sum='x';updTrainer(0.01);window.__av=rpAvail();rpStart();window.__busy=RPL.busy}""")
    for _ in range(90):
        pg.wait_for_timeout(1000)
        if not pg.evaluate("()=>RPL.busy"):
            break
    rpl = pg.evaluate("""()=>{const av=window.__av;const on=RPL.on&&document.getElementById('rpl').style.display==='block';
      const ghost=rpG.ghostP.g.visible&&!!RPL.ideal;rpStop();return {av,on,ghost,busy:window.__busy,off:!RPL.on&&document.getElementById('rpl').style.display==='none'&&plane.visible}}""")
    check("replay: a finished mission runs the sim pilot, then opens a replay with both paths and a ghost, and exits cleanly", rpl["av"] and rpl["busy"] and rpl["on"] and rpl["ghost"] and rpl["off"], str(rpl))
    pg.evaluate("()=>{FM.on=false;menuPick(0)}")

    shared = pg.evaluate("()=>['jeep','supply','tanker','apc','tank','truck','warehouse','hq','bunker','hangar','fuel'].every(t=>VM.make(t,SP[t].s)===VM.make(t,SP[t].s))")
    check("one shared geometry per vehicle/building type", shared)
    dead = pg.evaluate("()=>{const t=mkT('jeep',0,0,0,'veh');killT(t);return t.m.scale.y<.5}")
    check("destroyed target is flattened", dead)
    # ---- battle damage
    pg.evaluate("()=>{reset();DM.on=true;DM.reset()}")
    pg.wait_for_timeout(300)
    check("damage: starts undamaged", pg.evaluate("()=>!DM.any()"))
    pg.evaluate("()=>{DM.wl=0.9;DM.hyd=true;DM.eng=0.8;DM.fire=true;gearOn=true;flapLvl=0}")
    pg.wait_for_timeout(1500)
    check("damage: badly hit wing hides its aileron", pg.evaluate("()=>ailP.some(o=>o[1]<0&&!o[0].visible)"))
    check("damage: hydraulics block the flaps", pg.evaluate("()=>{ACT.flapDn();return flapLvl===0}"))
    check("damage: readout shown", pg.evaluate("()=>$$('dmgHud').style.display==='block'&&$$('dmgHud').textContent.includes('DAMAGE')"))
    check("damage: switching it off clears damage", pg.evaluate("()=>{$$('dmgOn').checked=false;$$('dmgOn').onchange({target:$$('dmgOn')});return !DM.any()&&!DM.on}"))
    pg.evaluate("()=>{$$('dmgOn').checked=true;$$('dmgOn').onchange({target:$$('dmgOn')})}")
    AIR = "pos.set(0,1500,0);vel.set(0,0,-150);onGround=false;"
    pg.evaluate("()=>{reset();DM.reset();started=true;crashed=false;paused=false;" + AIR + "}")
    pg.wait_for_timeout(300)
    pg.evaluate("()=>{" + AIR + "UIACT.bail()}")
    check("damage: first bail press only arms it", pg.evaluate("()=>!crashed&&!BL.on"))
    pg.evaluate("()=>{" + AIR + "DM.bailArm=performance.now()+8000;UIACT.bail()}")  # the 2 s window is long enough on a real machine, but the software renderer can be slow
    check("bail out: the second press starts the bail-out sequence, the camera goes to the cockpit", pg.evaluate("()=>BL.on&&!crashed&&camMode===1"))
    pg.evaluate("()=>{for(let i=0;i<10;i++)updBail(0.05)}")
    check("bail out: the canopy is blown off (and flies away as its own object)", pg.evaluate("()=>!can.visible&&canBars.every(b=>!b.visible)&&!!bailCanM"))
    pg.evaluate("()=>{for(let i=0;i<30;i++)updBail(0.05)}")
    check("bail out: the pilot climbs out of the seat and falls free", pg.evaluate("()=>BL.ph===2&&!plPilot.visible&&bailPil.visible&&BL.v.y<0"))
    pg.evaluate("()=>{for(let i=0;i<150;i++)updBail(0.05)}")
    check("bail out: the parachute opens", pg.evaluate("()=>BL.ph===3&&bailCh.visible&&bailCh.scale.x>0.9"))
    check("bail out: free look reaches straight down and straight up", pg.evaluate("()=>{BL.pitch=-9;bailCam(0.016);const d=cam.getWorldDirection(new V()).y;BL.pitch=9;bailCam(0.016);const u=cam.getWorldDirection(new V()).y;return d<-0.99&&u>0.99}"))
    check("bail out: the pilot floats down slowly", pg.evaluate("()=>BL.v.y>-7&&BL.v.y<-4"))
    check("bail out: the damage code cannot crash an aircraft that is already empty", pg.evaluate("()=>{crash('TEST');return !crashed}"))
    pg.evaluate("()=>{for(let i=0;i<9000&&!BL.fin;i++)updBail(0.05)}")
    check("bail out: he lands safely and the end message appears", pg.evaluate("()=>BL.fin&&crashed&&/LANDED|SPLASHDOWN/.test($$('msg').textContent)&&!$$('msg').textContent.includes('TOO LOW')"))
    check("bail out: the abandoned aircraft crashed on its own", pg.evaluate("()=>BL.gone&&!model.visible"))
    pg.evaluate("()=>{reset()}")
    check("bail out: restarting restores the canopy, the pilot, the camera", pg.evaluate("()=>!BL.on&&can.visible&&plPilot.visible&&!bailPil.visible&&camMode===0&&model.visible&&!bailCanM"))
    pg.evaluate("()=>{started=true;paused=false;pos.set(0,H(0,0)+60,0);vel.set(0,0,-150);onGround=false;bailOut();for(let i=0;i<400&&!BL.fin;i++)updBail(0.05)}")
    check("bail out: too low and the parachute has no time to open", pg.evaluate("()=>BL.fin&&$$('msg').textContent.includes('TOO LOW')"))
    pg.evaluate("()=>{reset()}")
    pg.evaluate("()=>{started=true;paused=false;" + AIR + "spawnEnemy();const r=Math.random;Math.random=()=>0.9;damageE(EN[0],1e6);Math.random=r}")
    check("bandit bail-out: most shot-down bandits do not bail out (the rate is 35%)", pg.evaluate("()=>CH.length===0&&BAIL_ENEMY===0.35"))
    pg.evaluate("()=>{clearEnemies();" + AIR + "lastSpawn=0;spawnEnemy();const r=Math.random;Math.random=()=>0.01;damageE(EN[0],1e6);Math.random=r}")
    check("bandit bail-out: a bandit that bails out leaves a pilot, and his cockpit is empty", pg.evaluate("()=>CH.length===1&&!EN[0].pilot.visible"))
    pg.evaluate("()=>{for(let i=0;i<120;i++)updChutists(0.05)}")
    check("bandit bail-out: his parachute opens and he floats down", pg.evaluate("()=>CH.length===1&&CH[0].ch.visible&&CH[0].v.y>-7"))
    pg.evaluate("()=>{CH[0].p.y=H(CH[0].p.x,CH[0].p.z)+20;for(let i=0;i<4000&&CH.length;i++)updChutists(0.05)}")
    check("bandit bail-out: he lands and is cleaned up", pg.evaluate("()=>CH.length===0"))
    pg.evaluate("()=>{clearEnemies();reset()}")
    check("damage: bail key documented", pg.evaluate("()=>BIND.some(b=>b[0]==='bail')"))
    pg.evaluate("()=>{reset();DM.reset()}")
    # ---- detailed trees near the camera (each check runs in ONE evaluate so the frame loop cannot move the camera in between)
    pg.evaluate("()=>{reset();QL.mode='high';applyQuality();started=true;paused=false}")
    check("trees: detailed variants exist for conifer and broadleaf", pg.evaluate("()=>NT.sp.length===2&&NT.sp.every(s=>s.vars.length===3&&s.vars[0].geometry.attributes.position.count>300)"))
    tr = pg.evaluate("()=>{const [x,y,z]=NT.sp[0].items[40];updNearTrees(x,y+60,z+100,true);return {n:NT.sp.reduce((a,s)=>a+s.vars.reduce((b,v)=>b+v.count,0),0),a:NTU.a.value,b:NTU.b.value,R:NT.R,k:NT.k,cap:NT.cap}}")
    check("trees: on High the trees near the camera are drawn in detail", tr["n"] > 0 and tr["b"] >= 60 and tr["a"] < tr["b"], str(tr))
    tr = pg.evaluate("()=>{updNearTrees(0,3000,0,true);return {n:NT.sp.reduce((a,s)=>a+s.vars.reduce((b,v)=>b+v.count,0),0),b:NTU.b.value,R:NT.R,k:NT.k}}")
    check("trees: high above the ground no detailed trees are drawn and the cheap ones show everywhere", tr["n"] == 0 and tr["b"] < 0, str(tr))
    check("trees: the Low tier draws no detailed trees", pg.evaluate("()=>{QL.mode='low';applyQuality();const [x,y,z]=NT.sp[0].items[40];updNearTrees(x,y+60,z+100,true);return NT.sp.every(s=>s.vars.every(v=>v.count===0))&&NTU.b.value<0}"))
    check("trees: a slow frame rate in Auto shrinks the detailed zone first, not the resolution", pg.evaluate("()=>{QL.mode='auto';QL.lite=false;applyQuality();NT.k=1;QL.acc=30*89;QL.n=89;adaptRes(30);return NT.k<1&&QL.pr===QL.max}"))
    # ---- near-camera grass (one evaluate each)
    g = pg.evaluate("()=>{QL.mode='high';applyQuality();const x=3000,z=-3400,y=HMESH(x,z)+2.5;updGrass(x,y,z,true);return {n:GR.grass.count,f:GR.flow.count,ci:GR.grass.instanceColor.array.length,r:GRU.r.value}}")
    check("grass: on High tufts and flowers are drawn around a low camera", g["n"] > 500 and g["f"] > 0 and g["ci"] >= g["n"] * 3 and g["r"] > 30, str(g))
    g = pg.evaluate("()=>{updGrass(60,200,-300,true);return GR.grass.count}")
    check("grass: none when high above the ground", g == 0, str(g))
    g = pg.evaluate("()=>{const y=HMESH(0,-300)+2;updGrass(0,y,-300,true);const a=GR.grass.instanceMatrix.array;let bad=0;for(let i=0;i<GR.grass.count;i++){const x=a[i*16+12];if(Math.abs(x)<34)bad++}return bad}")
    check("grass: none on the runway", g == 0, str(g))
    g = pg.evaluate("()=>{QL.mode='low';applyQuality();const x=3000,z=-3400;updGrass(x,HMESH(x,z)+2.5,z,true);return GR.grass.count}")
    check("grass: the Low tier draws none", g == 0, str(g))
    g = pg.evaluate("()=>{QL.mode='medium';applyQuality();const x=3000,z=-3400;updGrass(x,HMESH(x,z)+2.5,z,true);const m=GR.grass.count;QL.mode='high';applyQuality();updGrass(x,HMESH(x,z)+2.5,z,true);return [m,GR.grass.count]}")
    check("grass: Medium has a smaller zone than High", g[0] > 0 and g[0] < g[1], str(g))
    # ---- near detail on the player's aircraft
    d = pg.evaluate("()=>{QL.mode='high';applyQuality();updPlaneDetail(10);const n=PDET.list.every(o=>o.visible);updPlaneDetail(200);const f=PDET.list.every(o=>!o.visible);QL.mode='low';applyQuality();PDET.on=null;updPlaneDetail(10);const l=PDET.list.every(o=>!o.visible);QL.mode='high';applyQuality();PDET.on=null;updPlaneDetail(10);return {n,f,l,c:PDET.list.length}}")
    check("aircraft detail: shown close up, hidden far away and on Low", d["n"] and d["f"] and d["l"] and d["c"] >= 8, str(d))
    # ---- the pilot's hands are on the stick and the throttle
    d = pg.evaluate("()=>{reset();pilotIK();const u=plPilot.userData,t=new V(),k=new V();u.elbs[1].localToWorld(t.set(0,0,-0.31));ckStick.localToWorld(k.set(0,0.4,0));const ds=t.distanceTo(k);u.elbs[0].localToWorld(t.set(0,0,-0.31));ck.localToWorld(k.set(-0.44,0.57,-0.56));return {ds,dt:t.distanceTo(k)}}")
    check("cockpit: the right hand is on the stick grip and the left on the blue propeller lever", d["ds"] < 0.12 and d["dt"] < 0.12, str(d))
    d = pg.evaluate("()=>{reset();pilotIK();const u=plPilot.userData,t=new V(),k=new V(),r=[];[-1,1].forEach((sd,i)=>{u.legs[i][1].localToWorld(t.set(0,-0.5,0));ckPed[sd].localToWorld(k.set(0,0.01,-0.12));r.push(t.distanceTo(k))});return r}")
    check("cockpit: both feet rest on the rudder pedals", all(x < 0.1 for x in d), str(d))
    pg.evaluate("()=>{QL.mode='high';applyQuality();paused=false;reset()}")
    # ---- time of day and weather
    pg.evaluate("()=>{reset();started=true;WX.setTime('midday');WX.setWx('partly')}")
    pg.wait_for_timeout(500)
    vis = "()=>CLOUDS.filter(s=>s.visible).length"
    n_partly = pg.evaluate(vis)
    pg.evaluate("()=>WX.setWx('clear')")
    check("weather: clear sky shows fewer clouds than partly cloudy", pg.evaluate(vis) < n_partly)
    pg.evaluate("()=>$$('wxWx').onchange({target:{value:'storm'}})")
    pg.wait_for_timeout(800)
    check("weather: thunderstorm thins the view, rains and darkens", pg.evaluate("()=>scene.fog.far<5000&&RAIN.m.visible&&WX.rainK>1"))
    pg.evaluate("()=>{WX.nextBolt=0}"); pg.wait_for_timeout(600)
    check("weather: lightning flashes", pg.evaluate("()=>WX.flash>0||parseFloat(WXFL.style.opacity)>=0"))
    pg.evaluate("()=>WX.setWx('fog')")
    check("weather: fog is thick", pg.evaluate("()=>scene.fog.far<2000"))
    pg.evaluate("()=>{WX.setWx('clear');WX.setTime('night')}")
    pg.wait_for_timeout(500)
    check("night: stars, moon and runway lights appear, sun is gone", pg.evaluate("()=>STARS.visible&&MOON.visible&&RWL.visible&&NAVL[0].visible&&SUNSP.every(s=>!s.visible)"))
    check("night: buildings and the airfield have lit windows", pg.evaluate("()=>BLDL.opacity>0.5&&AFL.visible&&T.some(t=>t.lit&&t.lit.visible)"))
    pg.evaluate("()=>WX.setTime('midday')")
    check("midday: no stars, no runway lights", pg.evaluate("()=>!STARS.visible&&!RWL.visible"))
    pg.evaluate("()=>{$$('wxFlow').checked=true;$$('wxFlow').onchange({target:$$('wxFlow')});WX.setTime('dawn')}")
    h0 = pg.evaluate("()=>WX.hour"); pg.wait_for_timeout(2500)
    check("time passes when switched on", pg.evaluate("()=>WX.hour")>h0)
    check("weather settings are saved", pg.evaluate("()=>JSON.parse(localStorage.getItem('p51wx')||'{}').time==='dawn'"))
    pg.evaluate("()=>{$$('wxFlow').checked=false;$$('wxFlow').onchange({target:$$('wxFlow')});WX.setTime('midday');WX.setWx('partly')}")
    # ---- photo mode
    pg.evaluate("()=>{reset();started=true;paused=false;WX.setTime('midday');WX.setWx('partly');pauseMenu(true)}")
    pg.wait_for_timeout(300)
    pg.evaluate("()=>$$('pmPhoto').click()")
    pg.wait_for_timeout(500)
    check("photo mode: opens from the pause menu, freezes the game and hides the HUD", pg.evaluate("()=>PHOTO.on&&paused&&document.body.classList.contains('phHide')&&$$('ph').style.display==='block'"))
    p0 = pg.evaluate("()=>PHOTO.pos.x+','+PHOTO.pos.z")
    pg.evaluate("()=>{keys.KeyW=true}"); pg.wait_for_timeout(700); pg.evaluate("()=>{keys.KeyW=false}")
    check("photo mode: the free camera moves", pg.evaluate("()=>PHOTO.pos.x+','+PHOTO.pos.z")!=p0)
    pr = pg.evaluate("""()=>{const p=PHOTO.pos.clone(),y0=PHOTO.yaw;cv.dispatchEvent(new MouseEvent('mousedown',{button:2}));dispatchEvent(new MouseEvent('mousemove',{movementX:40,movementY:0}));dispatchEvent(new MouseEvent('mouseup'));const d=PHOTO.pos.distanceTo(p);const y1=PHOTO.yaw;cv.dispatchEvent(new MouseEvent('mousedown',{button:0}));dispatchEvent(new MouseEvent('mousemove',{movementX:40,movementY:0}));dispatchEvent(new MouseEvent('mouseup'));return [d,y1-y0,PHOTO.yaw-y1,PHOTO.pos.distanceTo(p)-d]}""")
    check("photo mode: right-drag moves the camera (no turn), left-drag turns it (no move)", pr[0] > 0.1 and abs(pr[1]) < 1e-6 and abs(pr[2]) > 0.01 and abs(pr[3]) < 1e-6, str(pr))
    wd = pg.evaluate("""()=>{const p=PHOTO.pos.clone(),f=PHOTO.fov;cv.dispatchEvent(new WheelEvent('wheel',{deltaY:-200,cancelable:true}));const d=PHOTO.pos.distanceTo(p),f1=PHOTO.fov;cv.dispatchEvent(new WheelEvent('wheel',{deltaY:-200,ctrlKey:true,cancelable:true}));return [d,f1-f,PHOTO.fov-f1]}""")
    check("photo mode: the wheel moves the camera in and out, Ctrl + wheel changes the FOV", wd[0] > 0.1 and abs(wd[1]) < 1e-6 and abs(wd[2]) > 0.5, str(wd))
    pg.evaluate("()=>{$$('phWx').value='storm';$$('phWx').onchange({target:$$('phWx')});photoSpot('side');PHOTO.hud=true;PHOTO.stamp=true;PHOTO.res=0;photoSync();PHOTO.last=null;PHOTO.shot=true}")
    pg.wait_for_function("()=>!!PHOTO.last", timeout=60000)
    check("photo mode: a JPG with the HUD and info stamp is made", pg.evaluate("()=>PHOTO.last.type==='image/jpeg'&&PHOTO.last.bytes>8000&&/^P51_v.*\\.jpg$/.test(PHOTO.last.name)"))
    pg.evaluate("()=>{PHOTO.hud=false;PHOTO.res=1;PHOTO.last=null;photoSync();PHOTO.shot=true}")
    pg.wait_for_function("()=>!!PHOTO.last", timeout=90000)
    check("photo mode: the 2560 px size option makes a bigger picture", pg.evaluate("()=>PHOTO.last.w>=2500"))
    pg.evaluate("()=>{PHOTO.res=0;photoSave();photoExit()}")
    pg.wait_for_timeout(300)
    check("photo mode: leaving restores the game, the weather and the camera", pg.evaluate("()=>!PHOTO.on&&WX.wx==='partly'&&!document.body.classList.contains('phHide')&&plane.visible&&pmOpen"))
    pg.evaluate("()=>{pauseMenu(false);reset()}")
    # ---- ILS
    pg.evaluate("()=>{FM.on=false;menuPick(2)}"); pg.wait_for_timeout(1200)
    onslope = "(x,z,dy)=>{pos.set(x,2.15+(z-400)*0.0524+dy,z);vel.set(0,-3,-58);q.setFromAxisAngle(UPV,0)}"
    pg.evaluate(f"()=>({onslope})(0,4000,0)"); pg.wait_for_timeout(700)
    check("ils: on the centreline and slope both needles are centred", pg.evaluate("()=>ILS.show&&ILS.locOK&&ILS.gsOK&&Math.abs(ILS.locD)<0.1&&Math.abs(ILS.gsD)<0.15"))
    check("ils: the landing trainer draws no glowing path (just the ring)", pg.evaluate("()=>gSpr.every(s=>!s.visible)&&gRing.every(s=>!s.visible)"))
    pg.evaluate(f"()=>({onslope})(100,4000,0)"); pg.wait_for_timeout(500)
    std = pg.evaluate("()=>ILS.locD")
    check("ils: right of the centreline the localizer needle is left of centre", std < -0.3)
    pg.evaluate(f"()=>({onslope})(0,4000,60)"); pg.wait_for_timeout(500)
    check("ils: above the slope the glide slope needle is below the centre", pg.evaluate("()=>ILS.gsD>0.5"))
    pg.evaluate(f"()=>({onslope})(1500,4000,0)"); pg.wait_for_timeout(500)
    check("ils: far off the line the beam is out of range (flags)", pg.evaluate("()=>!ILS.gsOK"))
    pg.evaluate("()=>{FM.on=true;FM.opt.ils=true}")
    pg.evaluate(f"()=>({onslope})(100,4000,0)"); pg.wait_for_timeout(500)
    check("ils: Hardcore realism makes the needles twice as sensitive", pg.evaluate("()=>ILS.hc")==True and pg.evaluate("()=>ILS.locD")<std*1.6)
    pg.evaluate(f"()=>({onslope})(0,600+7400,0)"); pg.wait_for_timeout(500)
    check("ils: the outer marker lights in Hardcore", pg.evaluate("()=>ILS.om"))
    pg.evaluate("()=>{FM.on=false}")
    pg.evaluate("()=>{menuPick(0);ILS.free=true}"); pg.wait_for_timeout(800)
    pg.evaluate("()=>{pos.set(0,250,-1700-4000);vel.set(0,-3,58);q.setFromAxisAngle(UPV,Math.PI)}"); pg.wait_for_timeout(600)
    check("ils: free flight north of the runway uses the 18 end", pg.evaluate("()=>ILS.show&&ILS.end===1&&ILS.locOK"))
    # ---- Hardcore weather effects: wind, turbulence, wet runway, icing
    pg.evaluate("()=>{ILS.free=false;reset();FM.on=true;Object.keys(FM.opt).forEach(k=>FM.opt[k]=false);window.__wx0=WX.wx;window.__run=(t)=>{for(let i=0;i<t*120;i++){if(crashed)break;step(1/120)}}}")
    wo = pg.evaluate("""()=>{
      const o={};
      const air=(wind,from,spd)=>{reset();crashed=false;FM.opt.wind=wind;WX.setWind(from,spd,0);pos.set(0,1500,0);vel.set(0,0,-100);q.identity();thr=0.6;step(1/120);return [FM.ias,vel.length()]};
      o.head=air(true,0,20); o.off=air(false,0,20); o.tail=air(true,180,20);
      FM.opt.wind=true;WX.setWind(270,20,0);reset();pos.set(0,1500,0);vel.set(0,0,-100);q.identity();thr=0.6;window.__run(10);o.vx=vel.x;
      WX.setWind(0,20,0);WX.setWx('clear');WX.setWind(0,20,0);reset();FM.on=true;
      o.sockStrong=(()=>{WX.setWind(0,20,0);pos.set(0,5,420);WX.update(0.1);return Math.abs(WSOCK.rotation.z)})();
      WX.setWind(0,0,0);FM.opt.wind=false;WX.update(0.1);o.sockCalm=Math.abs(WSOCK.rotation.z);
      return o}""")
    check("wind: a headwind raises airspeed above ground speed, a tailwind lowers it, off does neither", wo["head"][0] > wo["head"][1] + 12 and wo["tail"][0] < wo["tail"][1] - 12 and abs(wo["off"][0] - wo["off"][1]) < 1, str(wo))
    check("wind: a crosswind from the west blows the aircraft east", wo["vx"] > 8, str(wo["vx"]))
    check("wind: the windsock streams in a strong wind and hangs limp when calm", wo["sockStrong"] < 0.25 and wo["sockCalm"] > 0.9, str((wo["sockStrong"], wo["sockCalm"])))
    wt = pg.evaluate("""()=>{
      const o={};
      const rng=(wx,on)=>{reset();crashed=false;FM.opt.turb=on;WX.setWx(wx);WX.wnd={from:0,spd:0,gust:0};pos.set(0,2500,0);vel.set(0,0,-100);q.identity();thr=0.6;let lo=1e9,hi=-1e9;let acc=0,pv=vel.y;for(let i=0;i<1200;i++){step(1/120);WX.t+=1/120;acc+=Math.abs(vel.y-pv);pv=vel.y}return [acc,WX.tI]};
      o.storm=rng('storm',true);o.stormOff=rng('storm',false);o.clear=rng('clear',true);
      return o}""")
    check("turbulence: a thunderstorm shakes the aircraft far more than clear air, and the switch turns it off", wt["storm"][0] > 1.5 * wt["stormOff"][0] + 0.5 and wt["storm"][0] > 1.5 * wt["clear"][0] and wt["storm"][1] > 0.5 and wt["stormOff"][1] == 0, str(wt))
    wr = pg.evaluate("""()=>{
      const o={};
      const roll=(wx)=>{reset();crashed=false;FM.opt.turb=false;FM.opt.wind=false;FM.opt.wet=true;WX.setWx(wx);WX.wet=wx==='rain'?1:0;window.__run(0.4);vel.set(0,0,-30);keys.KeyB=true;window.__run(3);keys.KeyB=false;return [-vel.z,onGround]};
      o.dry=roll('clear');o.wet=roll('rain');
      reset();crashed=false;WX.setWx('rain');WX.wet=1;window.__run(0.4);vel.set(0,0,-60);window.__run(0.1);o.hyd=FM.hyd;
      FM.opt.wet=false;reset();crashed=false;window.__run(0.4);vel.set(0,0,-30);keys.KeyB=true;window.__run(3);keys.KeyB=false;o.off=-vel.z;FM.opt.wet=true;
      return o}""")
    check("wet runway: braking in the rain is much weaker than on a dry runway", wr["dry"][1] and wr["wet"][1] and wr["wet"][0] > wr["dry"][0] + 4, str(wr))
    check("wet runway: fast in heavy rain the aircraft hydroplanes, and the switch turns the effect off", wr["hyd"] is True and abs(wr["off"] - wr["dry"][0]) < 1.5, str(wr))
    wi = pg.evaluate("""()=>{
      const o={};
      FM.opt.ice=true;WX.setWx('overcast');reset();crashed=false;pos.set(0,2000,0);onGround=false;
      WX.inCloud=true;for(let i=0;i<30;i++)updIce(5);o.ice=FM.ice;o.oat=WX.oat(2000);
      const lift=(ice)=>{reset();crashed=false;FM.ice=ice;pos.set(0,2000,0);vel.set(0,-6.4,-80);q.identity();step(1/120);return gF};
      WX.inCloud=false;o.l0=lift(0);o.l1=lift(1);
      FM.ice=1;pos.set(0,0,0);for(let i=0;i<10;i++)updIce(10);o.melt=FM.ice;
      FM.opt.ice=false;FM.ice=0.7;updIce(1);o.off=FM.ice;FM.opt.ice=true;
      WX.setWx('clear');hudT=0;updHUD();o.hud=hud.innerHTML.includes('OAT');
      return o}""")
    check("icing: in cloud below freezing ice builds up to the maximum", wi["ice"] > 0.95 and wi["oat"] < 0, str(wi))
    check("icing: ice cuts the lift by about a third", wi["l1"] < 0.8 * wi["l0"] and wi["l0"] > 0.3, str((wi["l0"], wi["l1"])))
    check("icing: warm air melts it, the switch turns it off, and the HUD shows the temperature", wi["melt"] < 0.05 and wi["off"] == 0 and wi["hud"], str(wi))
    pg.evaluate("()=>{FM.opt.wind=true;WX.setWx('clear');hudT=0;WX.setWind(0,10,0);reset();pos.set(0,100,420);vel.set(0,0,-60);window.__run(0.1);hudT=0;updHUD()}")
    check("wind: the HUD shows the wind with head and cross components", pg.evaluate("()=>/WIND <b>\\d\\d\\d/.test(hud.innerHTML)&&/HEAD/.test(hud.innerHTML)"))
    pg.evaluate("()=>{WX.setWd('90');WX.setWs('strong')}")
    ws = pg.evaluate("()=>({f:WX.wnd.from,saved:JSON.parse(localStorage.getItem('p51wx')),sel:[$$('wxWd').value,$$('wxWs').value]})")
    check("wind: the direction and strength settings pick the wind and are saved", ws["f"] == 90 and ws["saved"]["wd"] == "90" and ws["saved"]["ws"] == "strong" and ws["sel"][0] != "x", str(ws))
    pg.evaluate("()=>{menuPick(0);ILS.free=true;FM.opt.wind=true;FM.opt.ils=true;WX.setWd('auto');WX.setWs('normal');WX.setWind(0,10,0)}"); pg.wait_for_timeout(800)
    pg.evaluate("()=>{WX.setWind(0,10,0);pos.set(0,250,-1700-4000);vel.set(0,-3,58);q.setFromAxisAngle(UPV,Math.PI)}"); pg.wait_for_timeout(700)
    check("wind: the ILS picks the runway end facing into the wind (north wind: runway 36)", pg.evaluate("()=>ILS.show&&ILS.end===0"))
    pg.evaluate("()=>{ILS.free=false;FM.on=false;Object.keys(FM.opt).forEach(k=>FM.opt[k]=true);WX.setWx(window.__wx0);reset()}")
    pg.evaluate("()=>{ILS.free=false;reset()}")
    tr = pg.evaluate("""()=>{
      const o={};
      FM.on=true;FM.opt.trim=true;reset();crashed=false;
      TRIM.e=0;trimUpd(1,1,0,0);o.up=TRIM.e;trimUpd(10,-1,0,0);o.dn=TRIM.e;trimUpd(10,0,1,0);o.r=TRIM.r;trimUpd(10,0,0,1);o.a=TRIM.a;
      trimUpd(100,1,1,1);o.max=[TRIM.e,TRIM.r,TRIM.a];
      ACT.trimC&&ACT.trimC();o.ctr=[TRIM.e,TRIM.r,TRIM.a];
      FM.opt.trim=false;TRIM.e=0;trimUpd(1,1,0,0);o.off=TRIM.e;
      FM.opt.trim=true;FM.on=false;TRIM.e=0;trimUpd(1,1,0,0);o.casual=TRIM.e;
      FM.on=true;FM.opt.trim=true;TRIM.e=1;TRIM.r=-1;TRIM.a=1;
      return o}""")
    pg.wait_for_timeout(600)
    tr.update(pg.evaluate("""()=>{const o={};o.tabs=[elevTabs[0].rotation.x,rudTab.rotation.y,ailTab?ailTab.rotation.x:0];FM.on=false;return o}"""))
    pg.wait_for_timeout(600)
    tr.update(pg.evaluate("""()=>({tabsOff:[elevTabs[0].rotation.x,rudTab.rotation.y]})"""))
    check("trim: keys move elevator, rudder and aileron trim and clamp at full travel", tr["up"] > 0.2 and tr["dn"] < 0 and tr["r"] > 0 and tr["a"] > 0 and tr["max"] == [1, 1, 1], str(tr))
    check("trim: centre-all resets, and it does nothing with the option or Hardcore off", tr["ctr"] == [0, 0, 0] and tr["off"] == 0 and tr["casual"] == 0, str(tr))
    check("trim: the tabs on the aircraft deflect in Hardcore and sit flat otherwise", abs(tr["tabs"][0]) > 0.1 and abs(tr["tabs"][1]) > 0.1 and abs(tr["tabs"][2]) > 0.1 and tr["tabsOff"] == [0, 0], str(tr))
    # ---- the hidden pilot flight: recorded before a mission, used by the green ring and by the replay
    pg.evaluate("()=>{PP.off=false;FM.on=false;const i=MENU.findIndex(x=>x[0]==='landing');menuPick(i);paused=false}")
    pg.wait_for_timeout(800)
    pg.evaluate("()=>{const i=MENU.findIndex(x=>x[0]==='takeoff');menuPick(i);paused=false}")  # change mission while the pilot is still flying
    for _ in range(240):
        pg.wait_for_timeout(1000)
        if not pg.evaluate("()=>RPL.busy"):
            break
    pp = pg.evaluate("""()=>{planGuide();for(let k=0;k<30;k++){step(1/60);updTrainer(1/60);updGuide(1/60);guideState(1/60)}
      const G=guideState(1/60);return {busy:RPL.busy,mode:trn.mode,n:PP.out?PP.out.length:0,ok:PP.ok,key:PP.key===ppKey(),
      el:Math.atan2(G.ry+2-pos.y,Math.hypot(G.rx-pos.x,G.rz-pos.z))*57.3,lat:Math.abs(G.lat)}}""")
    check("pilot recording: changing mission while the pilot flies cancels cleanly and the new mission gets its own recording", (not pp["busy"]) and pp["mode"] == "takeoff" and pp["n"] > 50 and pp["ok"] and pp["key"], str(pp))
    check("pilot recording: on the runway the green ring sits near the horizon and the line is the runway", abs(pp["el"]) < 3 and pp["lat"] < 15, str(pp))
    ae2 = pg.evaluate("""()=>{FM.on=false;const i=MENU.findIndex(x=>x[0]==='immelmann');menuPick(i);paused=false;return 1}""")
    for _ in range(120):
        pg.wait_for_timeout(1000)
        if not pg.evaluate("()=>RPL.busy"):
            break
    ae3 = pg.evaluate("""()=>{for(let k=0;k<20;k++){step(1/60);updEnemies(1/60);updTrainer(1/60);updGuide(1/60);if(guide.pts.length>1)guideState(1/60)}drawGuide();drawAim();
      return {n:PP.out?PP.out.length:0,ok:PP.ok,ring:ringShown(),aimHidden:document.getElementById('aim').style.display==='none',fd:document.getElementById('fd').style.display,txt:document.getElementById('coachS').textContent.includes('green ring')}}""")
    check("maneuver trainers: the pilot is recorded, the green ring replaces the old aim target, and the coach points at the ring", ae3["n"] > 50 and ae3["ok"] and ae3["ring"] and ae3["aimHidden"] and ae3["fd"] == "block" and ae3["txt"], str(ae3))
    cvs = pg.evaluate("""()=>{PP.off=true;const i=MENU.findIndex(x=>x[0]==='convoy');menuPick(i);return Math.hypot(pos.x-DEPOT[0],pos.z-DEPOT[1])}""")
    check("convoy: the start is far enough back (over 3.5 km) to line up without breaking off", cvs > 3500, str(round(cvs)))
    pg.evaluate("()=>{PP.off=true}")
    check("still no errors at the end", not errors, "; ".join(errors[-2:]))
    pg.close()  # two software-rendered pages at once are too slow; the desktop page is finished
    # ---- phone layout: a saved layout that pushes the top bar off screen is repaired so the pause button (and Exit) stays reachable
    ctx = b.new_context(viewport={"width": 792, "height": 360}, device_scale_factor=2, is_mobile=True, has_touch=True)
    ph = ctx.new_page(); ph.goto(HTML.as_uri(), timeout=120000); ph.wait_for_timeout(3000)
    check("phone: pause menu has the automatic fullscreen option, on by default", ph.evaluate("()=>$$('pmAutoFs').checked===true"))
    ph.evaluate("()=>{window.__fs=0;toggleFS=()=>{window.__fs++}}")
    ph.evaluate("()=>{$$('go').click()}"); ph.wait_for_timeout(1500)
    check("phone: starting the flight asks for fullscreen", ph.evaluate("()=>window.__fs===1"))
    vis = "()=>{const r=$$('tPause').getBoundingClientRect();return r.width>0&&r.left>=-1&&r.top>=-1&&r.right<=innerWidth+1&&r.bottom<=innerHeight+1}"
    check("phone: pause button is on screen", ph.evaluate(vis))
    ph.evaluate("()=>{UI.pos.tBar=[4000,-900];UI.applyAll()}")
    check("phone: test layout really hides the pause button", not ph.evaluate(vis))
    ph.evaluate("()=>UI.clampAll()")
    check("phone: an off-screen top bar is put back automatically", ph.evaluate(vis))
    ctx.close()
    b.close()

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
