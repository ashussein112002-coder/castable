/* Castable — cinematic layer. No dependencies. Everything here is decoration: if anything throws, the page still works.
   1. WebGL "silk" background (domain-warped noise, gold sheen) with mouse parallax; CSS-gradient fallback.
   2. Film grain overlay.
   3. Branded intro (home only, once per tab; ?intro=1 forces it, ?intro=0 skips it; any key/click skips it).
   4. Hero word reveal, magnetic primary button, cursor spotlight on glass panels, 3D tilt on cards, typewriter placeholder.
   Honours prefers-reduced-motion: static frame, no intro, no tilt. */
(function () {
  'use strict';
  var doc = document, root = doc.documentElement;
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var params = new URLSearchParams(location.search);

  /* ------------------------------------------------------------------ 1. silk background */
  function silk() {
    var c = doc.getElementById('fx');
    if (!c) return;
    var soft = parseFloat(c.getAttribute('data-soft') || '1');
    var gl = c.getContext('webgl', { antialias: false, alpha: false, powerPreference: 'low-power', preserveDrawingBuffer: false })
          || c.getContext('experimental-webgl');
    if (!gl) { c.classList.add('fallback'); return; }
    var VS = 'attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}';
    var FS = [
      'precision mediump float;',
      'uniform vec2 R;uniform float T;uniform vec2 M;uniform float S;',
      'float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}',
      'float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);',
      ' return mix(mix(h(i),h(i+vec2(1,0)),f.x),mix(h(i+vec2(0,1)),h(i+vec2(1,1)),f.x),f.y);}',
      'float fbm(vec2 p){float v=0.,a=.5;mat2 m=mat2(1.6,1.2,-1.2,1.6);',
      ' for(int i=0;i<5;i++){v+=a*n(p);p=m*p;a*=.5;}return v;}',
      'void main(){',
      ' vec2 uv=(gl_FragCoord.xy-.5*R)/R.y;',
      ' float t=T*.05;',
      ' vec2 p=uv*1.35+vec2(.2,.1)+(M-.5)*.18;',
      ' vec2 q=vec2(fbm(p+t),fbm(p+vec2(5.2,1.3)-t*.8));',
      ' vec2 r=vec2(fbm(p+3.2*q+vec2(1.7,9.2)+t*.6),fbm(p+3.2*q+vec2(8.3,2.8)-t*.5));',
      ' float f=fbm(p+2.6*r);',
      ' float fold=smoothstep(.28,.78,f);',                  // broad silk folds
      ' float ridge=pow(.5+.5*sin(f*11.+uv.x*2.2-T*.25),6.);', // moving highlight ridges
      ' vec3 base=vec3(0.,0.,0.);',                              // pure black
      ' vec3 deep=vec3(.05,.13,.02);',
      ' vec3 gold=vec3(.8,1.,0.);',
      ' vec3 cream=vec3(.93,1.,.55);',
      ' vec3 col=mix(base,deep,fold*.62);',
      ' col=mix(col,gold,ridge*fold*.5);',
      ' col=mix(col,cream,pow(ridge,2.)*fold*.28);',
      ' float teal=pow(fbm(p*.7-t*.9+2.),6.)*.35;',
      ' col+=vec3(.05,.08,.95)*teal;',
      ' float v=1.-smoothstep(.3,1.25,length(uv*vec2(.85,1.05)));',
      ' col*=mix(.45,1.,v);',
      ' col=mix(base,col,S);',
      ' gl_FragColor=vec4(col,1.);}'
    ].join('\n');
    function sh(type, src) { var s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s)); return s; }
    var prog;
    try {
      prog = gl.createProgram(); gl.attachShader(prog, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(prog));
    } catch (e) { c.classList.add('fallback'); return; }
    gl.useProgram(prog);
    var buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    var loc = gl.getAttribLocation(prog, 'p'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    var uR = gl.getUniformLocation(prog, 'R'), uT = gl.getUniformLocation(prog, 'T'), uM = gl.getUniformLocation(prog, 'M'), uS = gl.getUniformLocation(prog, 'S');
    var mx = .5, my = .5, tx = .5, ty = .5, running = true, w = 0, hgt = 0;
    var scale = Math.min(window.devicePixelRatio || 1, 1) * .5;      // half resolution: silky and cheap
    function resize() {
      w = Math.max(1, Math.floor(window.innerWidth * scale)); hgt = Math.max(1, Math.floor(window.innerHeight * scale));
      if (c.width !== w || c.height !== hgt) { c.width = w; c.height = hgt; gl.viewport(0, 0, w, hgt); }
    }
    window.addEventListener('resize', resize, { passive: true }); resize();
    window.addEventListener('pointermove', function (e) { tx = e.clientX / window.innerWidth; ty = 1 - e.clientY / window.innerHeight; }, { passive: true });
    doc.addEventListener('visibilitychange', function () { running = !doc.hidden; if (running) requestAnimationFrame(frame); });
    var t0 = performance.now(), last = 0;
    function frame(now) {
      if (!running) return;
      if (now - last < 33) { requestAnimationFrame(frame); return; }  // ~30 fps is plenty for silk
      last = now;
      mx += (tx - mx) * .04; my += (ty - my) * .04;
      gl.uniform2f(uR, w, hgt); gl.uniform1f(uT, (now - t0) / 1000); gl.uniform2f(uM, mx, my); gl.uniform1f(uS, soft);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      if (!reduced) requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    c.classList.add('on');
  }

  /* ------------------------------------------------------------------ 3. intro */
  function intro(done) {
    var el = doc.getElementById('intro');
    if (!el) return done();
    var force = params.get('intro');
    var seen = false;
    try { seen = sessionStorage.getItem('castable_intro') === '1'; } catch (e) {}
    if (reduced || force === '0' || (seen && force !== '1')) { el.remove(); return done(); }
    try { sessionStorage.setItem('castable_intro', '1'); } catch (e) {}
    root.classList.add('introing');
    var finished = false;
    function finish() {
      if (finished) return; finished = true;
      el.classList.add('out'); root.classList.remove('introing');
      setTimeout(function () { el.remove(); }, 700);
      done();
    }
    requestAnimationFrame(function () { el.classList.add('go'); });
    setTimeout(finish, 1750);
    el.addEventListener('click', finish); doc.addEventListener('keydown', finish, { once: true });
  }

  /* ------------------------------------------------------------------ 4. hero words */
  function splitWords(el) {
    if (!el || el.dataset.split) return; el.dataset.split = '1';
    var i = 0;
    function walk(node) {
      Array.prototype.slice.call(node.childNodes).forEach(function (n) {
        if (n.nodeType === 3) {
          var frag = doc.createDocumentFragment();
          n.textContent.split(/(\s+)/).forEach(function (piece) {
            if (!piece) return;
            if (/^\s+$/.test(piece)) { frag.appendChild(doc.createTextNode(' ')); return; }
            var o = doc.createElement('span'); o.className = 'w';
            var s = doc.createElement('span'); s.textContent = piece; s.style.transitionDelay = (i++ * 45) + 'ms';
            o.appendChild(s); frag.appendChild(o);
          });
          node.replaceChild(frag, n);
        } else if (n.nodeType === 1 && !n.classList.contains('w')) walk(n);
      });
    }
    walk(el);
  }
  function reveal(scope) {
    (scope || doc).querySelectorAll('.intro h1').forEach(function (h) {
      splitWords(h);
      h.classList.remove('revealed'); void h.offsetWidth;
      requestAnimationFrame(function () { h.classList.add('revealed'); });
    });
  }

  /* ------------------------------------------------------------------ 4b. pointer effects */
  var TILT = '.tilt, .facts > div, .rc, .kpis > *, .pitch, .card3d';
  function pointerFx() {
    if (reduced || !window.matchMedia('(hover: hover) and (pointer: fine)').matches) return;
    // spotlight on glass panels
    doc.addEventListener('pointermove', function (e) {
      var p = e.target.closest && e.target.closest('.panel, .spot');
      if (!p) return;
      var r = p.getBoundingClientRect();
      p.style.setProperty('--mx', (e.clientX - r.left) + 'px'); p.style.setProperty('--my', (e.clientY - r.top) + 'px');
    }, { passive: true });
    // magnetic primary buttons
    doc.querySelectorAll('button.primary, .btn.amber').forEach(function (b) {
      b.addEventListener('pointermove', function (e) {
        var r = b.getBoundingClientRect(), dx = (e.clientX - (r.left + r.width / 2)) / r.width, dy = (e.clientY - (r.top + r.height / 2)) / r.height;
        b.style.setProperty('--tx', (dx * 8) + 'px'); b.style.setProperty('--ty', (dy * 6) + 'px');
      });
      b.addEventListener('pointerleave', function () { b.style.setProperty('--tx', '0px'); b.style.setProperty('--ty', '0px'); });
    });
    // 3D tilt on cards
    doc.addEventListener('pointermove', function (e) {
      var t = e.target.closest && e.target.closest(TILT);
      if (!t) return;
      var r = t.getBoundingClientRect(), x = (e.clientX - r.left) / r.width - .5, y = (e.clientY - r.top) / r.height - .5;
      t.style.transform = 'perspective(900px) rotateX(' + (-y * 7).toFixed(2) + 'deg) rotateY(' + (x * 9).toFixed(2) + 'deg) translateZ(6px)';
    }, { passive: true });
    doc.addEventListener('pointerout', function (e) {
      var t = e.target.closest && e.target.closest(TILT);
      if (t && !(e.relatedTarget && t.contains(e.relatedTarget))) t.style.transform = '';
    }, { passive: true });
  }

  /* ------------------------------------------------------------------ 4c. typewriter placeholder */
  function typewriter() {
    var input = doc.getElementById('c_handle');
    if (!input || reduced) return;
    var names = ['karenwazen', 'mo_vlogs', 'anasala.family', 'yourhandle'], ni = 0, ci = 0, del = false, stop = false;
    input.addEventListener('focus', function () { stop = true; input.placeholder = 'yourhandle'; });
    (function tick() {
      if (stop || input.value) return;
      var word = names[ni];
      ci += del ? -1 : 1;
      input.placeholder = word.slice(0, ci) || ' ';
      var wait = del ? 45 : 95;
      if (!del && ci === word.length) { wait = 1500; del = true; }
      else if (del && ci === 0) { del = false; ni = (ni + 1) % names.length; wait = 350; }
      setTimeout(tick, wait);
    })();
  }

  /* ------------------------------------------------------------------ boot */
  function boot() {
    try { silk(); } catch (e) {}
    try { pointerFx(); } catch (e) {}
    intro(function () {
      try { reveal(); } catch (e) {}
      try { typewriter(); } catch (e) {}
    });
    // re-reveal the headline when the creator/brand switch changes which h1 is visible
    doc.querySelectorAll('.modes [role=tab]').forEach(function (tab) {
      tab.addEventListener('click', function () { setTimeout(function () { try { reveal(); } catch (e) {} }, 0); });
    });
  }
  if (doc.readyState === 'loading') doc.addEventListener('DOMContentLoaded', boot); else boot();
})();
