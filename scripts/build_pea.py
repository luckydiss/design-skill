"""HTML-страница -> SVG-сцена -> Photopea -> PSD с векторными фигурами, текстовыми слоями и масками.

Запуск: python build_pea.py <html> <out.psd> [--width W] [--pre JS_FILE] [--arg JSON] [--grid]
"""
import base64
import io
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, ImageOps
from playwright.sync_api import sync_playwright
from psd_tools import PSDImage

sys.path.insert(0, str(Path(__file__).parent))
from pea_api import HOST  # noqa: E402
from psd_guides import add_guides, column_guides
from scene_to_svg import SvgBuilder, load_image, fnum  # noqa: E402

TOOLS = Path(__file__).parent
SCENE_JS = (TOOLS / "scene.js").read_text(encoding="utf-8")
HIDE_CSS = """
html.__iso body *{visibility:hidden!important}
html.__iso .__sub, html.__iso .__sub *{visibility:visible!important}
html.__iso body{background:transparent!important}
html.__iso{background:transparent!important}
"""
INLINE_SVG_JS = r"""(i) => {
  const src = window.__S[i]; const cl = src.cloneNode(true);
  const sa = [src, ...src.querySelectorAll('*')], ca = [cl, ...cl.querySelectorAll('*')];
  const FONT = (fam, w) => { fam = fam.split(',')[0].replace(/["']/g,'').trim();
    if (fam === 'Manrope') return w >= 700 ? (w >= 800 ? 'Manrope-ExtraBold' : 'Manrope-Bold') : (w >= 600 ? 'Manrope-SemiBold' : 'Manrope-Regular');
    if (fam === 'Neucha' || fam === 'Caveat') return 'Neucha'; return w >= 600 ? 'Arial-BoldMT' : 'ArialMT'; };
  sa.forEach((e, k) => { const s = getComputedStyle(e), c = ca[k];
    for (const p of ['fill', 'stroke', 'stroke-width', 'fill-opacity', 'stroke-opacity', 'opacity', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin']) {
      let v = s.getPropertyValue(p); if (v && v !== 'normal') c.setAttribute(p, v); }
    if (e.tagName === 'text') { c.setAttribute('font-family', FONT(s.fontFamily, +s.fontWeight)); c.setAttribute('font-size', s.fontSize); c.removeAttribute('font-weight'); }
    c.removeAttribute('class'); c.removeAttribute('style'); });
  const vb = src.viewBox && src.viewBox.baseVal && src.viewBox.baseVal.width ? src.viewBox.baseVal : { x: 0, y: 0, width: src.width.baseVal.value, height: src.height.baseVal.value };
  return { inner: cl.innerHTML, vb: [vb.x, vb.y, vb.width, vb.height] };
}"""


class Builder(SvgBuilder):
    def __init__(self):
        self.p = sync_playwright().start()
        self.b = self.p.chromium.launch(channel="chrome")
        self.pea = None

    def _pea(self):
        if self.pea is None:
            pg = self.b.new_page(viewport={"width": 1700, "height": 1000})
            pg.route("http://local.host/", lambda r: r.fulfill(body=HOST, content_type="text/html"))
            pg.goto("http://local.host/")
            self.pea = pg
            self._wait(pg, 120)
        return self.pea

    @staticmethod
    def _wait(pg, timeout):
        import time
        t0 = time.time(); out = []
        while time.time() - t0 < timeout:
            for m in pg.evaluate("() => window.__msgs.splice(0)"):
                if m.get("txt") == "done":
                    return out
                out.append(base64.b64decode(m["bin"]) if "bin" in m else m.get("txt"))
            time.sleep(0.2)
        raise TimeoutError("Photopea timeout")

    def pea_run(self, script, timeout=600):
        pg = self._pea()
        pg.evaluate("(s) => window.__send(s)", script)
        return self._wait(pg, timeout)

    def pea_open(self, data: bytes, timeout=600):
        pg = self._pea()
        pg.evaluate("(b) => window.__sendBin(b)", base64.b64encode(data).decode())
        return self._wait(pg, timeout)

    # ---------- сцена ----------
    def scene(self, html, width, pre_js=None, pre_arg=None, wait=1500):
        pg = self.b.new_page(viewport={"width": width, "height": 900})
        pg.goto(Path(html).resolve().as_uri())
        pg.evaluate("document.fonts.ready.then(()=>1)"); pg.wait_for_timeout(wait)
        pg.evaluate("(mapping) => window.__PSD_FONT_MAP = mapping", getattr(self, "font_map", {}))
        pg.evaluate("async () => { await Promise.all(Array.from(document.images).map(im => im.decode().catch(() => null))); }")
        broken = pg.evaluate("() => Array.from(document.images).filter(im => !im.complete || im.naturalWidth === 0).map(im => im.src)")
        if broken: raise ValueError("Broken images: " + repr(broken))
        if pre_js:
            pg.evaluate(pre_js, pre_arg); pg.wait_for_timeout(400)
        H = pg.evaluate("Math.ceil(document.documentElement.scrollHeight)")
        pg.set_viewport_size({"width": width, "height": H}); pg.wait_for_timeout(300)
        flat = pg.screenshot(full_page=True)
        sc = pg.evaluate(SCENE_JS)
        for it in sc["items"]:
            if it["type"] == "svg":
                it["svg"] = pg.evaluate(INLINE_SVG_JS, it["idx"])
        # растровые фрагменты
        rasters = [it for it in sc["items"] if it["type"] == "raster"]
        if rasters:
            pg.add_style_tag(content=HIDE_CSS)
            pg.evaluate("document.documentElement.classList.add('__iso')")
            for it in rasters:
                pg.evaluate(f"window.__R[{it['idx']}].classList.add('__sub')")
                x0, y0 = max(0, int(it["x"]) - 2), max(0, int(it["y"]) - 2)
                x1, y1 = min(width, int(it["x"] + it["w"]) + 3), min(H, int(it["y"] + it["h"]) + 3)
                png = pg.screenshot(clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}, omit_background=True, full_page=True)
                pg.evaluate(f"window.__R[{it['idx']}].classList.remove('__sub')")
                im = Image.open(io.BytesIO(png)).convert("RGBA"); bb = im.getchannel("A").getbbox()
                if not bb:
                    it["skip"] = True; continue
                im = im.crop(bb); buf = io.BytesIO(); im.save(buf, "PNG")
                it.update(x=x0 + bb[0], y=y0 + bb[1], w=im.width, h=im.height, data="data:image/png;base64," + base64.b64encode(buf.getvalue()).decode())
        pg.close()
        sc["height"] = H
        return sc, flat

    # ---------- SVG ----------
    # ---------- сборка ----------
    def build(self, html, out_psd, out_png=None, width=1440, pre_js=None, pre_arg=None, guides=None, flat_png=None):
        sc, flat = self.scene(html, width, pre_js, pre_arg)
        if flat_png:
            Path(flat_png).write_bytes(flat)
        svg, names, texts = self.to_svg(sc)
        Path(out_psd).with_suffix(".svg").write_text(svg, encoding="utf-8") if "--keep-svg" in sys.argv else None
        self.pea_open(svg.encode("utf-8"))
        post = ("var M=" + json.dumps(names, ensure_ascii=False) + ";var T=" + json.dumps(texts, ensure_ascii=False) + ";" + r"""
function walk(ls){for(var i=0;i<ls.length;i++){var l=ls[i];var n=l.name;
 if(T[n]&&l.kind==LayerKind.TEXT){var t=l.textItem;t.contents=T[n].c;if(T[n].lead){t.useAutoLeading=false;t.leading=T[n].lead;}if(T[n].tr){t.tracking=T[n].tr;}}
 if(n.indexOf('Clip-Path: ')==0){var k=n.substr(11);if(M[k])l.name='Маска: '+M[k][0];}
 else if(M[n]){l.name=M[n][0];if(M[n][1])l.visible=false;if(M[n][2]!==undefined&&M[n][2]<0.999){l.opacity=M[n][2]*100;var pr=l.parent;if(pr&&pr.typename=='LayerSet'&&pr.name.indexOf('Clip-Path')==0)pr.opacity=100;}}
 if(l.typename=='LayerSet')walk(l.layers);}}
var d=app.activeDocument; walk(d.layers); d.saveToOE('psd');""")
        res = self.pea_run(post, timeout=900)
        psd = [r for r in res if isinstance(r, bytes)]
        if not psd:
            raise RuntimeError("no PSD from Photopea: " + str(res)[:300])
        data = psd[-1]
        if guides:
            p = PSDImage.open(io.BytesIO(data)); add_guides(p._record, guides)
            buf = io.BytesIO(); p._record.write(buf); data = buf.getvalue()
        Path(out_psd).parent.mkdir(parents=True, exist_ok=True)
        Path(out_psd).write_bytes(data)
        if out_png:
            res = self.pea_run("app.activeDocument.saveToOE('png');", timeout=300)
            pngs = [r for r in res if isinstance(r, bytes)]
            if pngs:
                Path(out_png).write_bytes(pngs[-1])
        self.pea_run("app.activeDocument.close(SaveOptions.DONOTSAVECHANGES);", timeout=120)
        kinds = {}
        for it in sc["items"]:
            kinds[it["type"]] = kinds.get(it["type"], 0) + 1
        print(Path(out_psd).name, len(data) // 1024, "KB", kinds, flush=True)

    def close(self):
        self.b.close(); self.p.stop()


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(description='HTML -> editable PSD through Photopea. Only run where standalone browser automation is allowed.')
    parser.add_argument('html',type=Path)
    parser.add_argument('psd',type=Path)
    parser.add_argument('--width',type=int,default=1440)
    parser.add_argument('--container',type=float)
    parser.add_argument('--columns',type=int,default=12)
    parser.add_argument('--gutter',type=float,default=30)
    parser.add_argument('--grid',action='store_true')
    parser.add_argument('--pre',type=Path)
    parser.add_argument('--arg',type=Path,help='JSON file with pre-script arguments')
    parser.add_argument('--fonts',type=Path,help='JSON mapping family -> weight/style -> PostScript name')
    parser.add_argument('--keep-svg',action='store_true')
    args=parser.parse_args()
    args.psd.parent.mkdir(parents=True,exist_ok=True)
    b=Builder()
    b.font_map=json.loads(args.fonts.read_text(encoding='utf8')) if args.fonts else {}
    try:
        guides=column_guides(args.width,args.container or args.width*1170/1440,args.columns,gutter=args.gutter) if args.grid else None
        b.build(args.html,args.psd,args.psd.with_suffix('.png'),width=args.width,
                pre_js=args.pre.read_text(encoding='utf8') if args.pre else None,
                pre_arg=json.loads(args.arg.read_text(encoding='utf8')) if args.arg else None,
                guides=guides,flat_png=args.psd.with_name(args.psd.stem+'_browser.png'))
    finally:
        b.close()
