(() => {
  "use strict";
  const NS = "http://www.w3.org/2000/svg";
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s) => document.querySelector(s);
  const el = (tag, attrs = {}, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };

  /* ================= ward plan ================= */
  const svg = $("#plan svg");
  if (svg) initPlan();

  function initPlan() {
    const gW = $("#walls"), gR = $("#ranges"), gL = $("#links"), gP = $("#packets"), gN = $("#nodes");
    const tip = $("#tip");
    const RANGE = 330, SEND_MS = 3000, UP = 330, DOWN = 520, ALERT = 640;

    // ---- rooms ----
    const rooms = [];
    const RW = 230;
    for (let i = 0; i < 4; i++) rooms.push({ name: `Room ${i + 1}`, x: 20 + i * RW, y: 20, w: RW, h: 260, top: true });
    for (let i = 0; i < 4; i++) rooms.push({ name: `Room ${i + 5}`, x: 20 + i * RW, y: 360, w: RW, h: 260, top: false });
    const station = { name: "the nurse station", x: 940, y: 20, w: 240, h: 600 };

    for (const r of rooms) {
      el("rect", { x: r.x, y: r.y, width: r.w, height: r.h }, gW);
      // bed against the outer wall
      const by = r.top ? r.y + 18 : r.y + r.h - 18 - 110;
      el("rect", { class: "furn", x: r.x + 18, y: by, width: 72, height: 110, rx: 4 }, gW);
      el("rect", { class: "furn", x: r.x + 26, y: r.top ? by + 8 : by + 110 - 30, width: 56, height: 22, rx: 6 }, gW);
      // door: gap + leaf + swing arc
      const dx = r.x + 150, wy = r.top ? r.y + r.h : r.y, dir = r.top ? -1 : 1;
      el("line", { class: "gap", x1: dx, y1: wy, x2: dx + 52, y2: wy }, gW);
      el("line", { class: "leaf", x1: dx, y1: wy, x2: dx, y2: wy + dir * 52 }, gW);
      el("path", { class: "door", d: `M${dx + 52} ${wy} A52 52 0 0 ${r.top ? 0 : 1} ${dx} ${wy + dir * 52}` }, gW);
      const t = el("text", { class: "room-l", x: r.x + 104, y: r.top ? r.y + 32 : r.y + r.h - 18 }, gW);
      t.textContent = r.name;
    }
    // nurse station shell with corridor opening
    el("rect", { x: station.x, y: station.y, width: station.w, height: station.h }, gW);
    el("line", { class: "gap", x1: 940, y1: 286, x2: 940, y2: 354 }, gW);
    el("rect", { class: "furn", x: 975, y: 232, width: 170, height: 64, rx: 4 }, gW);
    const nsl = el("text", { class: "ns-l", x: 962, y: 56 }, gW); nsl.textContent = "Nurse station";
    const flash = el("rect", { class: "ns-flash", x: station.x + 6, y: station.y + 6, width: station.w - 12, height: station.h - 12 }, gW);
    const BR = { x: 1012, y: 264 }, PI = { x: 1102, y: 264 };
    el("rect", { class: "hw", x: BR.x - 14, y: BR.y - 7, width: 28, height: 14, rx: 3 }, gW);
    el("rect", { class: "hw", x: PI.x - 22, y: PI.y - 14, width: 44, height: 28, rx: 3 }, gW);
    const l1 = el("text", { class: "hw-l", x: BR.x, y: BR.y + 48, "text-anchor": "middle" }, gW); l1.textContent = "Gateway";
    const l2 = el("text", { class: "hw-l", x: PI.x, y: PI.y + 48, "text-anchor": "middle" }, gW); l2.textContent = "Raspberry Pi";

    // ---- bands ----
    const START = [
      [165, 170], [395, 165], [615, 175], [850, 150],
      [165, 470], [400, 500], [845, 480], [560, 322],
    ];
    const nodes = START.map(([x, y], i) => ({
      id: i, x, y, bpm: 64 + Math.round(Math.random() * 20), parent: null, hops: Infinity,
      next: performance.now() + 400 + Math.random() * SEND_MS, fallUntil: 0,
    }));

    const roomOf = (n) => {
      for (const r of rooms) if (n.x >= r.x && n.x <= r.x + r.w && n.y >= r.y && n.y <= r.y + r.h) return r.name;
      if (n.x >= station.x) return "the nurse station";
      return "the corridor";
    };
    const who = (n) => { const r = roomOf(n); return r.startsWith("Room") ? `${r} resident` : `Resident in ${r}`; };
    const theWho = (n) => { const r = roomOf(n); return r.startsWith("Room") ? `the ${r} resident` : `the resident in ${r}`; };
    const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

    // ---- RPL-like parent selection: fewest hops, then best links ----
    function buildTree() {
      nodes.forEach((n) => { n.parent = null; n.hops = Infinity; n._c = Infinity; });
      const done = new Set();
      const all = [{ id: "br", x: BR.x, y: BR.y, hops: 0, _c: 0 }, ...nodes];
      all[0]._c = 0;
      while (true) {
        let best = null;
        for (const a of all) if (!done.has(a.id) && a._c < Infinity && (!best || a._c < best._c)) best = a;
        if (!best) break;
        done.add(best.id);
        for (const n of nodes) {
          if (done.has(n.id)) continue;
          const d = dist(best, n);
          if (d > RANGE) continue;
          const c = best._c + 1 + 0.35 * (d / RANGE);
          if (c < n._c) { n._c = c; n.parent = best; n.hops = best.hops + 1; }
        }
      }
    }

    const linkEls = nodes.map(() => el("line", {}, gL));
    const nodeEls = nodes.map((n) => {
      const g = el("g", { class: "node", tabindex: "0", role: "button" }, gN);
      el("circle", { class: "hit", r: 26 }, g);
      el("circle", { class: "ring", r: 13 }, g);
      el("circle", { class: "body", r: 13 }, g);
      el("circle", { class: "core", r: 5 }, g);
      g.addEventListener("pointerdown", (e) => startDrag(e, n));
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fall(n); } });
      g.addEventListener("pointerenter", () => { hover = n; showTip(n); });
      g.addEventListener("pointerleave", () => { if (hover === n) { hover = null; if (!drag) hideTip(); } });
      g.addEventListener("focus", () => { hover = n; showTip(n); });
      g.addEventListener("blur", () => { if (hover === n) { hover = null; hideTip(); } });
      return g;
    });
    const rangeEl = el("circle", { r: RANGE, cx: -999, cy: -999 }, gR);

    function render() {
      nodes.forEach((n, i) => {
        const g = nodeEls[i];
        g.setAttribute("transform", `translate(${n.x} ${n.y})`);
        const online = n.parent !== null;
        const falling = n.fallUntil > performance.now();
        g.classList.toggle("offline", !online);
        g.classList.toggle("fall", falling);
        g.setAttribute("aria-label", `${who(n)}, ${online ? n.hops + (n.hops === 1 ? " hop" : " hops") + " from the gateway" : "out of range"}. Press Enter to simulate a fall.`);
        const L = linkEls[i];
        if (online) {
          const p = n.parent.id === "br" ? BR : n.parent;
          L.setAttribute("x1", n.x); L.setAttribute("y1", n.y); L.setAttribute("x2", p.x); L.setAttribute("y2", p.y);
          L.style.display = "";
        } else L.style.display = "none";
        L.classList.toggle("alert", falling);
      });
      // colour the whole alert path
      nodes.forEach((n) => {
        if (n.fallUntil > performance.now()) {
          let c = n.parent;
          while (c && c.id !== "br") { linkEls[c.id].classList.add("alert"); c = c.parent; }
        }
      });
      $("#s-online").textContent = nodes.filter((n) => n.parent).length;
      if (hover) showTip(hover);
    }

    // ---- tooltip ----
    let hover = null;
    function showTip(n) {
      const online = n.parent !== null;
      const falling = n.fallUntil > performance.now();
      tip.innerHTML = `<b>${who(n)}</b>` +
        (falling ? "Fall detected, alert sent" : `${n.bpm} bpm`) + "<br>" +
        (online ? `${n.hops} ${n.hops === 1 ? "hop" : "hops"} to the gateway, RPL rank ${256 * (n.hops + 1)}`
                : "Out of range of every band. It rejoins as soon as one is near.");
      tip.hidden = false;
      const box = svg.getBoundingClientRect(), host = svg.parentElement;
      const sx = box.width / 1200, w = tip.offsetWidth, h = tip.offsetHeight;
      const x = n.x * sx, y = n.y * sx;
      const left = Math.max(w / 2 + 6, Math.min(box.width - w / 2 - 6, x));
      const below = y - h - 22 < 0;
      tip.style.left = `${left}px`;
      tip.style.top = `${y}px`;
      tip.style.transform = below ? "translate(-50%, 22px)" : "translate(-50%, calc(-100% - 18px))";
    }
    function hideTip() { tip.hidden = true; }

    // ---- dragging ----
    let drag = null;
    function toSvg(e) {
      const pt = svg.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
      return pt.matrixTransform(svg.getScreenCTM().inverse());
    }
    function startDrag(e, n) {
      e.preventDefault();
      const p = toSvg(e);
      drag = { n, sx: p.x, sy: p.y, ox: n.x, oy: n.y, moved: false, id: e.pointerId };
      nodeEls[n.id].setPointerCapture(e.pointerId);
      nodeEls[n.id].addEventListener("pointermove", onMove);
      nodeEls[n.id].addEventListener("pointerup", endDrag, { once: true });
      nodeEls[n.id].addEventListener("pointercancel", endDrag, { once: true });
    }
    function onMove(e) {
      if (!drag) return;
      const p = toSvg(e);
      const dx = p.x - drag.sx, dy = p.y - drag.sy;
      if (!drag.moved && Math.hypot(dx, dy) < 6) return;
      drag.moved = true;
      const n = drag.n;
      n.x = Math.max(36, Math.min(1164, drag.ox + dx));
      n.y = Math.max(36, Math.min(604, drag.oy + dy));
      const before = n.parent && n.parent.id;
      buildTree();
      rangeEl.setAttribute("cx", n.x); rangeEl.setAttribute("cy", n.y);
      rangeEl.classList.toggle("out", !n.parent);
      if ((n.parent && n.parent.id) !== before) logParent(n);
      render();
    }
    function endDrag() {
      const g = nodeEls[drag.n.id];
      g.removeEventListener("pointermove", onMove);
      rangeEl.setAttribute("cx", -999);
      const d = drag; drag = null;
      if (!d.moved) fall(d.n);
      else if (hover !== d.n) hideTip();
    }
    function logParent(n) {
      if (!n.parent) log(`${who(n)} is out of range. It will rejoin as soon as a band is near.`);
      else if (n.parent.id === "br") log(`${who(n)} now talks to the gateway directly.`);
      else log(`${who(n)} re-routed through ${theWho(n.parent)}'s band, ${n.hops} hops out.`);
    }

    // ---- packets ----
    const packets = [];
    let rx = 0, acks = 0, falls = 0;
    function pathUp(n) {
      const pts = [{ x: n.x, y: n.y }];
      let c = n.parent;
      while (c && c.id !== "br") { pts.push({ x: c.x, y: c.y }); c = c.parent; }
      pts.push(BR, PI);
      return pts;
    }
    function send(n, kind = "up") {
      if (!n.parent) return false;
      const pts = pathUp(n);
      if (reduced) { arrive({ kind, n, pts }); return true; }
      const r = kind === "alarm" ? 8 : 5;
      packets.push({ kind, n, pts, seg: 0, t: 0, speed: kind === "alarm" ? ALERT : UP, el: el("circle", { class: "pkt" + (kind === "alarm" ? " alarm" : ""), r }, gP) });
      return true;
    }
    function arrive(p) {
      if (p.kind === "up") {
        rx++; $("#s-rx").textContent = rx;
        const back = [...p.pts].reverse();
        if (reduced) { acks++; $("#s-ack").textContent = acks; return; }
        packets.push({ kind: "ack", n: p.n, pts: back, seg: 0, t: 0, speed: DOWN, el: el("circle", { class: "pkt ack", r: 4 }, gP) });
      } else if (p.kind === "ack") {
        acks++; $("#s-ack").textContent = acks;
      } else if (p.kind === "alarm") {
        falls++; $("#s-fall").textContent = falls;
        flash.classList.remove("on"); void flash.getBBox(); flash.classList.add("on");
        const hops = p.pts.length - 2;
        log(`Fall alert from ${theWho(p.n)} reached the nurse station over ${hops} ${hops === 1 ? "hop" : "hops"}.`, true);
      }
    }
    function fall(n) {
      if (!n.parent) { log(`${who(n)} is out of range, so the alert would wait until a band is near.`, true); return; }
      n.fallUntil = performance.now() + 7000;
      n.bpm = 112 + Math.round(Math.random() * 14);
      send(n, "alarm");
      log(`Fall detected on ${theWho(n)}'s band. Alert on its way.`, true);
      render();
      setTimeout(() => { n.bpm = 64 + Math.round(Math.random() * 20); render(); }, 7100);
    }
    function log(msg, alarm = false) {
      const L = $("#s-log"); L.textContent = msg; L.classList.toggle("alarm", alarm);
    }

    // ---- loop ----
    let last = performance.now(), visible = true;
    function tick(now) {
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      if (visible) {
        for (const n of nodes) {
          if (now >= n.next) {
            n.next = now + SEND_MS;
            n.bpm = Math.max(55, Math.min(130, n.bpm + Math.round((Math.random() - 0.5) * 3)));
            send(n);
          }
        }
        for (let i = packets.length - 1; i >= 0; i--) {
          const p = packets[i];
          let move = p.speed * dt;
          while (move > 0 && p.seg < p.pts.length - 1) {
            const a = p.pts[p.seg], b = p.pts[p.seg + 1];
            const len = Math.max(1, Math.hypot(b.x - a.x, b.y - a.y));
            const rem = (1 - p.t) * len;
            if (move >= rem) { move -= rem; p.seg++; p.t = 0; }
            else { p.t += move / len; move = 0; }
          }
          if (p.seg >= p.pts.length - 1) { p.el.remove(); packets.splice(i, 1); arrive(p); continue; }
          const a = p.pts[p.seg], b = p.pts[p.seg + 1];
          p.el.setAttribute("cx", a.x + (b.x - a.x) * p.t);
          p.el.setAttribute("cy", a.y + (b.y - a.y) * p.t);
        }
        if (nodes.some((n) => n.fallUntil && n.fallUntil < now)) {
          nodes.forEach((n) => { if (n.fallUntil && n.fallUntil < now) n.fallUntil = 0; });
          linkEls.forEach((l) => l.classList.remove("alert"));
          render();
        }
      }
      requestAnimationFrame(tick);
    }

    if ("IntersectionObserver" in window) {
      new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) { const t = performance.now(); nodes.forEach((n) => (n.next = t + Math.random() * SEND_MS)); } }, { threshold: 0.05 }).observe(svg);
    }
    document.addEventListener("visibilitychange", () => { last = performance.now(); });

    $("#b-fall").addEventListener("click", () => {
      const online = nodes.filter((n) => n.parent && n.fallUntil < performance.now());
      if (online.length) fall(online[Math.floor(Math.random() * online.length)]);
    });
    $("#b-reset").addEventListener("click", () => {
      nodes.forEach((n, i) => { n.x = START[i][0]; n.y = START[i][1]; n.fallUntil = 0; });
      packets.forEach((p) => p.el.remove()); packets.length = 0;
      linkEls.forEach((l) => l.classList.remove("alert"));
      buildTree(); render(); log("Ward reset. All bands back in their rooms.");
    });

    buildTree(); render();
    setTimeout(() => log("All bands joined. Readings are flowing to the nurse station."), 1500);
    requestAnimationFrame(tick);
  }

  /* ================= fall-detection trade-off ================= */
  const roc = $("#roc");
  if (roc && window.SWEEP) initRoc();

  function initRoc() {
    const data = window.SWEEP; // [thr, recall, far]
    const W = 560, H = 380, m = { l: 64, r: 22, t: 22, b: 58 };
    const X0 = 0, X1 = 35, Y0 = 85, Y1 = 100;
    const sx = (v) => m.l + ((v - X0) / (X1 - X0)) * (W - m.l - m.r);
    const sy = (v) => H - m.b - ((v - Y0) / (Y1 - Y0)) * (H - m.t - m.b);
    const g = el("g", { class: "grid" }, roc);
    for (let x = 0; x <= 35; x += 5) {
      el("line", { x1: sx(x), x2: sx(x), y1: m.t, y2: H - m.b }, g);
      const t = el("text", { class: "tick", x: sx(x), y: H - m.b + 22, "text-anchor": "middle" }, roc); t.textContent = x + "%";
    }
    for (let y = 85; y <= 100; y += 5) {
      el("line", { x1: m.l, x2: W - m.r, y1: sy(y), y2: sy(y) }, g);
      const t = el("text", { class: "tick", x: m.l - 10, y: sy(y) + 4, "text-anchor": "end" }, roc); t.textContent = y + "%";
    }
    el("line", { class: "axis", x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b }, roc);
    el("line", { class: "axis", x1: m.l, x2: m.l, y1: m.t, y2: H - m.b }, roc);
    const xl = el("text", { class: "alab", x: (m.l + W - m.r) / 2, y: H - 12, "text-anchor": "middle" }, roc); xl.textContent = "Everyday activities flagged as falls";
    const yl = el("text", { class: "alab", x: 18, y: (m.t + H - m.b) / 2, "text-anchor": "middle", transform: `rotate(-90 18 ${(m.t + H - m.b) / 2})` }, roc); yl.textContent = "Falls caught";

    const pts = data.filter((d) => d[2] * 100 <= X1 && d[1] * 100 >= Y0);
    el("path", { class: "curve", d: pts.map((d, i) => `${i ? "L" : "M"}${sx(d[2] * 100).toFixed(1)} ${sy(d[1] * 100).toFixed(1)}`).join(" ") }, roc);
    // final design marker (nested CV with stillness check)
    const fx = sx(9.77), fy = sy(94.88);
    el("rect", { class: "final", x: fx - 6, y: fy - 6, width: 12, height: 12, transform: `rotate(45 ${fx} ${fy})` }, roc);
    const lx = sx(1.2), ly = sy(98.4);
    el("polyline", { class: "guide", points: `${fx - 4},${fy - 8} ${fx - 4},${ly + 22} ${lx + 4},${ly + 22}`, style: "stroke: var(--ink); fill: none" }, roc);
    const fl = el("text", { class: "final-l", x: lx + 4, y: ly }, roc); fl.textContent = "Final design,";
    const fl2 = el("text", { class: "final-l", x: lx + 4, y: ly + 16 }, roc); fl2.textContent = "with stillness check";

    const gv = el("line", { class: "guide" }, roc), gh = el("line", { class: "guide" }, roc);
    const dot = el("circle", { class: "cur", r: 8 }, roc);
    const input = $("#thr"), out = $("#thr-o"), read = $("#readout");
    function update() {
      const t = parseFloat(input.value);
      const d = data.reduce((a, b) => (Math.abs(b[0] - t) < Math.abs(a[0] - t) ? b : a));
      const x = sx(Math.min(X1, d[2] * 100)), y = sy(Math.max(Y0, d[1] * 100));
      dot.setAttribute("cx", x); dot.setAttribute("cy", y);
      gv.setAttribute("x1", x); gv.setAttribute("x2", x); gv.setAttribute("y1", y); gv.setAttribute("y2", H - m.b);
      gh.setAttribute("x1", m.l); gh.setAttribute("x2", x); gh.setAttribute("y1", y); gh.setAttribute("y2", y);
      out.textContent = t.toFixed(2);
      read.innerHTML = `At a threshold of ${t.toFixed(2)}, the model catches <strong>${(d[1] * 100).toFixed(1)}%</strong> of falls and raises a false alarm on <strong>${(d[2] * 100).toFixed(1)}%</strong> of everyday-activity trials.`;
    }
    input.addEventListener("input", update);
    update();
  }

  /* ================= citation ================= */
  const cite = $("#cite");
  if (cite) cite.addEventListener("click", async () => {
    const bib = `@software{adithiya2026wearablemesh,
  author  = {G, Tanush Adithiya},
  title   = {Edge-Intelligent Health Monitoring over Adaptive Low-Power and Lossy Networks: privacy-preserving wearable IoT mesh},
  year    = {2026},
  url     = {https://github.com/sapphire-rapid/privacy-preserving-wearable},
  version = {1.0.0}
}`;
    const ok = $("#cite-ok");
    try { await navigator.clipboard.writeText(bib); ok.textContent = "Citation copied"; }
    catch { ok.textContent = "Copy failed. The citation is in CITATION.cff on GitHub."; }
    setTimeout(() => (ok.textContent = ""), 3000);
  });
})();
