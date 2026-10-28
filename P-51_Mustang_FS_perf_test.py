#!/usr/bin/env python3
"""P-51_Mustang_FS_perf_test.py - performance check for the P-51 Mustang flight simulator.

Runs the simulator's own physics step headless (no real-time wait) and prints the numbers that
the About page compares with the real P-51D: sea-level climb rate (clean and loaded), top speed
and cruise speeds at 300 m, the indicated top speed at 7,600 m, and the engine-off glide ratio at 175 mph (real: about 14.8).

Usage:  python3 P-51_Mustang_FS_perf_test.py [hc|std|both] [html path]
        hc   = Hardcore mode (real-performance options on)    std = standard arcade mode
Needs:  pip install playwright  (and its chromium browser). Edit CHROME below if the browser
        is somewhere else; leave it as None to use Playwright's own copy.

Reference values (real P-51D, from the flight-characteristics document and the blueprints):
  climb at sea level about 16 m/s (3,200 ft/min); top speed 703 km/h at 7,600 m (true speed),
  roughly 580-610 km/h near sea level; cruise about 583 km/h true speed at altitude.
Hardcore mode is meant to land within a few percent of these. Standard mode is intentionally
a little faster (arcade) and the About page documents that.

Trim is set for the current speed (as a pilot would); the Hardcore trim tabs otherwise change the hands-off speed.
Wind, turbulence, wet runway and icing are switched off so the numbers repeat from run to run.
Method: each case resets the plane in the air, holds a pitch angle with a simple controller,
and reads the climb rate over 15 s (best of four pitch angles). Top speed and cruise are
found by pinning altitude and letting the speed settle. Engine heat is reset every step so a
long run is not cut short by overheating.
"""
import sys, json
from playwright.sync_api import sync_playwright

CHROME = None  # e.g. '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
HTML = 'file:///mnt/user-data/outputs/P-51_Mustang_FS.html'

JS = """(mode)=>{
  const out={};paused=true;FM.on=(mode==='hc');for(const k of ['wind','turb','wet','ice'])FM.opt[k]=false;
  const run=(t,hold)=>{for(let i=0;i<t*120;i++){if(crashed)break;
    const pit=Math.asin(Math.max(-1,Math.min(1,fwd.y)));pad.p=Math.max(-1,Math.min(1,(hold-pit)*5));pad.r=0;pad.y=0;
    step(1/120);FM.eT=0;FM.fuel=Math.max(FM.fuel,0.6)}};
  const start=(h,spd,t,clean)=>{reset();paused=true;pos.set(0,h,0);q.identity();vel.set(0,0,-spd);thr=t;FM.reset();FM.fuel=0.6;onGround=false;gearOn=false;flapLvl=0;fl=0;if(clean){rkN=6;bmN=2}axes();autoTrim(spd)};
  const level=(h,t,clean)=>{start(h,150,t,clean);for(let k=0;k<45;k++){autoTrim(FM.ias||150);run(2,0);pos.y=h;vel.y=0}return Math.round(FM.ias*3.6)};
  const climb=(h,clean)=>{let best=-99;for(const a of [0.1,0.15,0.2,0.26]){start(h,140,1,clean);run(40,a);const y0=pos.y;run(15,a);best=Math.max(best,(pos.y-y0)/15)}return Math.round(best*10)/10};
  out.climb_clean_m_s=climb(300,true);out.climb_loaded_m_s=climb(300,false);
  out.top_300m_kmh_ias=level(300,1,true);out.cruise65_kmh=level(300,0.65,true);out.cruise80_kmh=level(300,0.8,true);out.cruise90_kmh=level(300,0.9,true);
  out.top_7600m_kmh_ias=level(7600,1,true);
  /* glide: engine at idle, attitude held fixed, 90 s to settle, then 30 s measured; interpolated to 175 mph indicated */
  const glide=(deg)=>{start(2000,75,0,true);thr=0;const qa=new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1,0,0),deg*Math.PI/180);let p0=null;
    for(let i=0;i<120*90;i++){q.copy(qa);pad.p=pad.r=pad.y=0;step(1/120);FM.eT=0;q.copy(qa);if(i===120*60)p0=pos.clone()}
    const dy=p0.y-pos.y;return [FM.ias/0.44704,Math.hypot(pos.x-p0.x,pos.z-p0.z)/dy]};
  {const a=glide(0),b=glide(2);out.glide_ratio_175mph=Math.round((a[1]+(b[1]-a[1])*(175-a[0])/(b[0]-a[0]))*10)/10}
  return out}"""

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else 'both'
    html = sys.argv[2] if len(sys.argv) > 2 else HTML
    if not html.startswith('file:'): html = 'file://' + html
    modes = ['std', 'hc'] if mode == 'both' else [mode]
    with sync_playwright() as p:
        kw = dict(args=['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--no-sandbox'])
        if CHROME: kw['executable_path'] = CHROME
        b = p.chromium.launch(**kw)
        for m in modes:
            pg = b.new_page(viewport={'width': 700, 'height': 400})
            pg.goto(html); pg.wait_for_timeout(2000)
            pg.evaluate("()=>{document.getElementById('go').click()}"); pg.wait_for_timeout(2000)
            print(('HARDCORE' if m == 'hc' else 'STANDARD'), json.dumps(pg.evaluate(JS, m)))
            pg.close()
        b.close()

if __name__ == '__main__':
    main()
