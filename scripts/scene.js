// Разбор отрисованной страницы на элементы для PSD: прямоугольники (векторные фигуры),
// текстовые блоки (строки, базовые линии, шрифт), изображения, вложенные SVG и растровые фрагменты.
(() => {
  const items = [];
  window.__R = [];                          // элементы для растрового запасного варианта
  const WIRE = document.documentElement.classList.contains('wire');
  const cs = e => getComputedStyle(e);
  const sx = window.scrollX, sy = window.scrollY;
  const INLINE = d => d === 'inline' || d === 'contents';
  const short = (s, n = 34) => (s = s.replace(/\s+/g, ' ').trim(), s.length > n ? s.slice(0, n - 1) + '…' : s);
  const parseColor = c => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null; const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number); return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 }; };
  const hex = c => '#' + [c.r, c.g, c.b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const opacityOf = e => { let o = 1; for (let p = e; p && p !== document.documentElement; p = p.parentElement) o *= +cs(p).opacity; return o; };
  const groupsOf = e => { const g = []; for (let p = e.parentElement; p && p !== document.body; p = p.parentElement) if (p.dataset.g) g.unshift(p.dataset.g); return g; };
  const hiddenOf = e => { for (let p = e; p && p !== document.body; p = p.parentElement) if (p.dataset.hidden === '1') return true; return false; };
  const visible = e => { const s = cs(e); if (s.display === 'none' || s.visibility === 'hidden') return false; const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const box = e => { const r = e.getBoundingClientRect(); return { x: r.left + sx, y: r.top + sy, w: r.width, h: r.height }; };
  const nameOf = e => {
    if (e.dataset.n) return e.dataset.n;
    const t = e.tagName, s = short(e.innerText || e.textContent || '');
    if (/^H[1-6]$/.test(t)) return `Заголовок ${t}: ${s}`;
    if (t === 'IMG' || e.classList.contains('media')) return 'Изображение' + (e.dataset.alt ? ': ' + e.dataset.alt : '');
    if (t === 'svg') return 'Иконка' + (e.dataset.alt ? ': ' + e.dataset.alt : '');
    if (e.classList.contains('btn')) return `Кнопка: ${s}`;
    if (t === 'P') return `Текст: ${s}`;
    if (t === 'A') return `Ссылка: ${s}`;
    if (t === 'LI') return `Пункт: ${s}`;
    return s ? `Текст: ${s}` : 'Элемент';
  };
  // ---- шрифты: CSS -> PostScript-имя в Photopea ----
  const FONT = (fam, w, it) => {
    fam = fam.split(',')[0].replace(/["']/g, '').trim();
    w = +w;
    const custom = (window.__PSD_FONT_MAP || {})[fam];
    if (custom) {
      const key=String(w)+(it ? 'italic' : '');
      if (custom[key]) return custom[key];
      throw new Error('No PostScript font mapping for '+fam+' '+key);
    }
    const pick = (base, map) => { let best = null, d = 1e9; for (const k in map) { const dd = Math.abs(+k - w); if (dd < d) { d = dd; best = map[k]; } } return base + '-' + best; };
    if (fam === 'Manrope') return pick('Manrope', { 400: 'Regular', 500: 'Medium', 600: 'SemiBold', 700: 'Bold', 800: 'ExtraBold' });
    if (fam === 'Cormorant Garamond') return it ? 'CormorantGaramond-MediumItalic' : pick('CormorantGaramond', { 500: 'Medium', 600: 'SemiBold', 700: 'Bold' });
    if (fam === 'Noto Serif SC') return w >= 600 ? 'NotoSerifSC-Bold' : 'NotoSerifSC-Medium';
    if (fam === 'Caveat') return 'Caveat-Medium';
    if (fam === 'Neucha') return 'Neucha';
    const simple = { 'Montserrat': 'Montserrat', 'Open Sans': 'OpenSans', 'PT Sans': 'PTSans', 'Raleway': 'Raleway', 'Playfair Display': 'PlayfairDisplay', 'PT Serif': 'PTSerif', 'Lora': 'Lora', 'Prata': 'Prata' };
    if (simple[fam]) return simple[fam] + (fam === 'Prata' ? '-Regular' : (w >= 600 ? '-Bold' : '-Regular'));
    if (fam === 'Arial' || fam === 'sans-serif') return w >= 600 ? 'Arial-BoldMT' : 'ArialMT';
    throw new Error('Add verified PostScript font mapping for '+fam);
  };
  const CJK = /[㐀-鿿豈-﫿]/;
  const ctx = document.createElement('canvas').getContext('2d');

  // ---- текстовые блоки ----
  const blockOf = n => { let p = n.parentElement; while (p && INLINE(cs(p).display)) p = p.parentElement; return p; };
  const textBlocks = new Map();   // блок -> [текстовые узлы]
  const tw = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = tw.nextNode(); n; n = tw.nextNode()) {
    if (!n.textContent.trim()) continue;
    const pe = n.parentElement; if (!pe || pe.closest('svg,script,style,[data-skip]')) continue;
    const s = cs(pe); if (s.visibility === 'hidden' || s.display === 'none') continue;
    const col = parseColor(s.color); if (!col || col.a === 0) continue;
    const b = blockOf(n); if (!textBlocks.has(b)) textBlocks.set(b, []); textBlocks.get(b).push(n);
  }
  const textItem = (blk, nodes) => {
    // доминирующий стиль = стиль самого длинного узла
    let main = nodes[0]; for (const n of nodes) if (n.textContent.trim().length > main.textContent.trim().length) main = n;
    const s = cs(main.parentElement), bs = cs(blk);
    const size = parseFloat(s.fontSize);
    const upper = s.textTransform === 'uppercase';
    // слова с координатами
    const words = [];
    for (const n of nodes) {
      const ts = cs(n.parentElement), up = ts.textTransform === 'uppercase';
      const txt = n.textContent; const re = /\S+/g; let m;
      while ((m = re.exec(txt))) {
        const r = document.createRange(); r.setStart(n, m.index); r.setEnd(n, m.index + m[0].length);
        const rects = [...r.getClientRects()].filter(q => q.width > 0);
        if (!rects.length) continue;
        // слово может переноситься по символам (вертикальный текст) — разобьём по прямоугольникам
        const vert = (cs(blk).writingMode || '').startsWith('vertical');
        if (rects.length > 1 || vert) {
          for (let i = 0; i < m[0].length; i++) { const rr = document.createRange(); rr.setStart(n, m.index + i); rr.setEnd(n, m.index + i + 1); const q = rr.getClientRects()[0]; if (q) words.push({ t: up ? m[0][i].toUpperCase() : m[0][i], x: q.left + sx, y: q.top + sy, r: q.right + sx, h: q.height, glue: i > 0 }); }
        } else words.push({ t: up ? m[0].toUpperCase() : m[0], x: rects[0].left + sx, y: rects[0].top + sy, r: rects[0].right + sx, h: rects[0].height });
      }
    }
    if (!words.length) return null;
    const vertical = (bs.writingMode || '').startsWith('vertical');
    const lines = [];
    for (const w of words) {
      const L = lines[lines.length - 1];
      if (!vertical && L && Math.abs(L.y - w.y) < size * 0.5) { L.t += (w.glue || w.x - L.r < size * 0.12 ? '' : ' ') + w.t; L.r = w.r; }
      else lines.push({ t: w.t, x: w.x, y: w.y, r: w.r, h: w.h });
    }
    ctx.font = `${s.fontStyle} ${s.fontWeight} ${s.fontSize} ${s.fontFamily}`;
    const mt = ctx.measureText('Hgд');
    const asc = mt.fontBoundingBoxAscent, desc = mt.fontBoundingBoxDescent;
    const baseOf = L => L.y + (L.h - (asc + desc)) / 2 + asc;
    const lh = lines.length > 1 ? (baseOf(lines[lines.length - 1]) - baseOf(lines[0])) / (lines.length - 1) : (parseFloat(s.lineHeight) || size * 1.3);
    let align = bs.textAlign; if (align === 'start') align = 'left';
    const minx = Math.min(...lines.map(l => l.x)), maxr = Math.max(...lines.map(l => l.r));
    let x = minx;
    const multiAligned = lines.length > 1 && Math.abs(lines[0].x - lines[1].x) > 2;
    if (vertical) { align = 'center'; x = (minx + maxr) / 2; }
    else if (align === 'center' || (multiAligned && Math.abs((lines[0].x + lines[0].r) / 2 - (lines[1].x + lines[1].r) / 2) < 3)) { align = 'center'; x = (lines[0].x + lines[0].r) / 2; }
    else if (align === 'right' || align === 'end') { align = 'right'; x = maxr; }
    else align = 'left';
    const full = lines.map(l => l.t).join('\r');
    let font = FONT(s.fontFamily, s.fontWeight, s.fontStyle === 'italic');
    if (CJK.test(full) && !font.startsWith('NotoSerifSC') && !(window.__PSD_FONT_MAP || {})[s.fontFamily.split(',')[0].replace(/["']/g,'').trim()]) throw new Error('Split CJK text into its own block with a verified CJK font: '+full.slice(0,60));
    const ls = parseFloat(s.letterSpacing) || 0;
    return { type: 'text', lines: lines.map(l => l.t), x, y: baseOf(lines[0]), size, lead: lh, font, color: hex(parseColor(s.color)),
             opacity: parseColor(s.color).a * opacityOf(main.parentElement), tracking: Math.round(ls / size * 1000), align,
             bbox: { x: minx, y: lines[0].y, w: maxr - minx, h: lines[lines.length - 1].y + lines[lines.length - 1].h - lines[0].y } };
  };

  // ---- собственная отрисовка элемента: фон, рамки, градиенты ----
  const gradient = bg => {
    const m = bg.match(/^linear-gradient\((.*)\)$/); if (!m || /repeating/.test(bg)) return null;
    const parts = m[1].split(/,(?![^(]*\))/).map(s => s.trim());
    let ang = 180; if (/deg$/.test(parts[0])) { ang = parseFloat(parts.shift()); } else if (/^to /.test(parts[0])) { const d = parts.shift(); ang = { 'to top': 0, 'to right': 90, 'to bottom': 180, 'to left': 270 }[d] ?? 180; }
    const stops = parts.map((p, i, a) => { const c = p.match(/rgba?\([^)]+\)|#[0-9a-f]+/i)[0]; const pc = p.match(/(-?[\d.]+)%/); return { c: parseColor(c), o: pc ? +pc[1] / 100 : i / (a.length - 1) }; });
    return { ang, stops };
  };
  const ownPaint = (e, name, groups, extra = {}) => {
    const s = cs(e), b = box(e), op = opacityOf(e);
    const out = [];
    const bg = parseColor(s.backgroundColor);
    const rr = s.borderTopLeftRadius; const rad = Math.min(/%$/.test(rr) ? parseFloat(rr) / 100 * Math.min(b.w, b.h) : (parseFloat(rr) || 0), b.w / 2, b.h / 2);
    const bi = s.backgroundImage;
    const bw = ['Top', 'Right', 'Bottom', 'Left'].map(k => s['border' + k + 'Style'] !== 'none' ? parseFloat(s['border' + k + 'Width']) : 0);
    const bc = ['Top', 'Right', 'Bottom', 'Left'].map(k => parseColor(s['border' + k + 'Color']));
    const uniform = bw.every(v => v === bw[0]) && bc.every(c => c && hex(c) === hex(bc[0]) && c.a === bc[0].a);
    let grad = null;
    if (bi && bi !== 'none') { grad = gradient(bi); if (!grad && !WIRE) return [{ raster: true }]; }
    const fill = bg && bg.a > 0 ? { c: hex(bg), a: bg.a } : null;
    if (fill || grad || (uniform && bw[0] > 0)) {
      const it = { type: 'rect', name, groups, x: b.x, y: b.y, w: b.w, h: b.h, rx: rad, fill, grad, opacity: op };
      if (uniform && bw[0] > 0 && bc[0] && bc[0].a > 0) it.stroke = { c: hex(bc[0]), a: bc[0].a, w: bw[0] };
      out.push(it);
    }
    if (!uniform) ['Top', 'Right', 'Bottom', 'Left'].forEach((k, i) => {
      if (!bw[i] || !bc[i] || bc[i].a === 0) return;
      const r = i === 0 ? [b.x, b.y, b.w, bw[i]] : i === 2 ? [b.x, b.y + b.h - bw[i], b.w, bw[i]] : i === 1 ? [b.x + b.w - bw[i], b.y, bw[i], b.h] : [b.x, b.y, bw[i], b.h];
      out.push({ type: 'rect', name: `${name} — линия`, groups, x: r[0], y: r[1], w: r[2], h: r[3], rx: 0, fill: { c: hex(bc[i]), a: bc[i].a }, opacity: op });
    });
    const ol = parseFloat(s.outlineWidth); const oc = parseColor(s.outlineColor);
    if (s.outlineStyle !== 'none' && ol > 0 && oc) { const off = parseFloat(s.outlineOffset) || 0; out.push({ type: 'rect', name: name + ' — контур', groups, x: b.x - off - ol / 2, y: b.y - off - ol / 2, w: b.w + 2 * off + ol, h: b.h + 2 * off + ol, rx: 0, fill: null, stroke: { c: hex(oc), a: oc.a, w: ol }, opacity: op }); }
    return out;
  };

  // ---- обход ----
  const emitted = new Set();
  const pushRaster = (e, name, groups) => { window.__R.push(e); const b = box(e); items.push({ type: 'raster', idx: window.__R.length - 1, name, groups, x: b.x, y: b.y, w: b.w, h: b.h, hidden: hiddenOf(e) }); };
  const emitText = (blk, groups, nameHint) => {
    if (!textBlocks.has(blk) || emitted.has(blk)) return;
    emitted.add(blk);
    const it = textItem(blk, textBlocks.get(blk)); if (!it) return;
    it.name = nameHint || nameOf(blk); it.groups = groups; it.hidden = hiddenOf(blk); items.push(it);
  };
  const walk = (e, groups) => {
    if (e.nodeType !== 1 || e.hasAttribute('data-skip')) return;
    const s = cs(e); if (s.display === 'none') return;
    const t = e.tagName;
    const isAtom = e.dataset.l !== undefined || e.classList.contains('btn');
    let g = groups;
    if (e.dataset.g) g = groups.concat(e.dataset.g);
    const hidden = hiddenOf(e);
    if (t === 'svg') {
      if (!visible(e)) return;
      const nm = nameOf(e);
      if (e.closest('[data-raster]') || e.dataset.raster !== undefined) pushRaster(e, nm, g);
      else { const b = box(e); items.push({ type: 'svg', name: nm, groups: g, x: b.x, y: b.y, w: b.w, h: b.h, idx: (window.__S = window.__S || []).push(e) - 1, opacity: opacityOf(e), hidden }); }
      return;
    }
    if (t === 'IMG') {
      if (!visible(e) || +s.opacity === 0) return;
      const cl = box(e.parentElement.classList.contains('media') ? e.parentElement : e), ib = e.getBoundingClientRect();
      const nw = e.naturalWidth, nh = e.naturalHeight;
      const fit = s.objectFit, pos = s.objectPosition.split(' ').map(v => parseFloat(v) / 100);
      let sc = fit === 'contain' ? Math.min(ib.width / nw, ib.height / nh) : fit === 'fill' ? null : Math.max(ib.width / nw, ib.height / nh);
      let dw, dh; if (sc === null) { dw = ib.width; dh = ib.height; } else { dw = nw * sc; dh = nh * sc; }
      const dx = ib.left + sx + (ib.width - dw) * pos[0], dy = ib.top + sy + (ib.height - dh) * pos[1];
      const pr = cs(e.parentElement); const rad = /%$/.test(pr.borderTopLeftRadius) ? 0 : (parseFloat(pr.borderTopLeftRadius) || 0);
      items.push({ type: 'image', name: nameOf(e.parentElement.classList.contains('media') ? e.parentElement : e), groups: g, src: e.currentSrc || e.src,
        x: dx, y: dy, w: dw, h: dh, clip: { x: Math.max(cl.x, ib.left + sx), y: Math.max(cl.y, ib.top + sy), w: Math.min(cl.w, ib.width), h: Math.min(cl.h, ib.height), rx: rad },
        opacity: opacityOf(e), sepia: /sepia/.test(s.filter) ? parseFloat(s.filter.match(/sepia\(([\d.]+)/)[1]) : 0, hidden });
      return;
    }
    if (!visible(e) && !e.children.length) return;
    if (s.transform && s.transform !== 'none' && !e.closest('[data-raster]') && t !== 'svg' && !/^matrix\(1, 0, 0, 1,/.test(s.transform)) {
      pushRaster(e, nameOf(e), g); return;   // повёрнутые элементы — растром
    }
    if (e.dataset.raster !== undefined) { pushRaster(e, nameOf(e), g); return; }
    // атомарный элемент (кнопка, поле, виджет) — отдельная группа слоёв
    let ag = g;
    if (isAtom) ag = g.concat(nameOf(e));
    const before = items.length;
    const nm = isAtom ? 'Подложка' : (e.dataset.bg || (e.dataset.g ? 'Подложка: ' + e.dataset.g : (e.classList.contains('media') ? nameOf(e) : 'Подложка')));
    // заглушка изображения в прототипе
    if (WIRE && e.classList.contains('media')) {
      const b = box(e);
      items.push({ type: 'rect', name: 'Заглушка изображения', groups: ag, x: b.x, y: b.y, w: b.w, h: b.h, rx: 0, fill: { c: '#d0d0d0', a: 1 }, stroke: { c: '#9e9e9e', a: 1, w: 1 }, opacity: 1 });
      items.push({ type: 'path', name: 'Крест заглушки', groups: ag, d: `M${b.x} ${b.y} L${b.x + b.w} ${b.y + b.h} M${b.x + b.w} ${b.y} L${b.x} ${b.y + b.h}`, stroke: { c: '#9e9e9e', w: 1.5 }, opacity: 1 });
    } else if (INLINE(s.display)) {
      const bgc = parseColor(s.backgroundColor);
      if (bgc && bgc.a > 0) [...e.getClientRects()].forEach(r => items.push({ type: 'rect', name: WIRE ? 'Плашка текста' : 'Подложка', groups: ag, x: r.left + sx, y: r.top + sy, w: r.width, h: r.height, rx: 0, fill: { c: hex(bgc), a: bgc.a }, opacity: opacityOf(e), hidden }));
    } else if (visible(e)) {
      const own = ownPaint(e, nm, ag);
      if (own.length === 1 && own[0].raster) { pushRaster(e, nameOf(e), g); return; }
      own.forEach(o => { o.hidden = hidden; items.push(o); });
    }
    // текст, принадлежащий этому блоку
    if (textBlocks.has(e)) emitText(e, ag, isAtom ? null : null);
    for (const c of e.children) walk(c, ag);
    // если атом дал ровно один слой — группа не нужна
    if (isAtom) {
      const made = items.slice(before);
      if (made.length === 1) { made[0].groups = g; made[0].name = nameOf(e); }
      else if (made.length === 0) { /* пусто */ }
    }
  };
  for (const c of document.body.children) walk(c, []);
  const bg = parseColor(cs(document.body).backgroundColor);
  return { width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight, bg: bg && bg.a > 0 ? hex(bg) : '#ffffff', items };
})()
