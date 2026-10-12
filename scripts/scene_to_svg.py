"""Scene JSON -> SVG and a Photopea post-import script. No browser automation."""
import argparse
import base64
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape
from PIL import Image, ImageOps

def fnum(value):
    return f"{value:.2f}".rstrip("0").rstrip(".")

def load_image(src, width, height, sepia=0):
    if src.startswith('data:'):
        metadata, payload=src.split(',',1)
        raw=base64.b64decode(payload) if ';base64' in metadata else urllib.parse.unquote_to_bytes(payload)
        image=Image.open(io.BytesIO(raw))
    elif src.startswith('file:'):
        path=urllib.request.url2pathname(urllib.parse.urlparse(src).path)
        image=Image.open(path)
    elif src.startswith(('http:', 'https:')):
        raise ValueError('Download remote images to D: first, then reference a local file.')
    else:
        image=Image.open(Path(src))
    # Keep meaningful alpha rather than turning it into a black JPEG background.
    image=image.convert('RGBA' if image.mode in ('RGBA','LA') or 'transparency' in image.info else 'RGB')
    tw=int(min(image.width,max(64,width*1.5)))
    if tw < image.width:
        image=image.resize((tw,max(1,round(image.height*tw/image.width))),Image.Resampling.LANCZOS)
    if sepia:
        alpha=image.getchannel('A') if image.mode=='RGBA' else None
        rgb=image.convert('RGB')
        tinted=ImageOps.colorize(ImageOps.grayscale(rgb),'#2b1d0e','#f5e6c8')
        image=Image.blend(rgb,tinted,min(1,sepia))
        if alpha is not None: image.putalpha(alpha)
    buffer=io.BytesIO()
    if image.mode=='RGBA':
        image.save(buffer,'PNG'); mime='image/png'
    else:
        image.save(buffer,'JPEG',quality=90); mime='image/jpeg'
    return 'data:'+mime+';base64,'+base64.b64encode(buffer.getvalue()).decode()

def post_script(names,texts,export_format='psd'):
    # Values are JSON literals, including quoted Cyrillic text and newlines.
    return 'var M='+json.dumps(names,ensure_ascii=False)+';var T='+json.dumps(texts,ensure_ascii=False)+';'+r"""
function walk(ls){for(var i=0;i<ls.length;i++){var l=ls[i],n=l.name;
 if(T[n]&&l.kind==LayerKind.TEXT){var t=l.textItem;t.contents=T[n].c;if(T[n].lead){t.useAutoLeading=false;t.leading=T[n].lead;}if(T[n].tr){t.tracking=T[n].tr;}}
 if(n.indexOf('Clip-Path: ')==0){var k=n.substr(11);if(M[k])l.name='Маска: '+M[k][0];}
 else if(M[n]){l.name=M[n][0];if(M[n][1])l.visible=false;if(M[n][2]!==undefined&&M[n][2]<0.999){l.opacity=M[n][2]*100;var pr=l.parent;if(pr&&pr.typename=='LayerSet'&&pr.name.indexOf('Clip-Path')==0)pr.opacity=100;}}
 if(l.typename=='LayerSet')walk(l.layers);}}
walk(app.activeDocument.layers);
"""+'app.activeDocument.saveToOE('+json.dumps(export_format)+');'

class SvgBuilder:
    def to_svg(self, sc):
        W, H = sc["width"], sc["height"]
        defs, body = [], []
        names, texts = {}, {}
        n = [0]

        def nid(prefix="e"):
            n[0] += 1; return f"{prefix}{n[0]}"

        # дерево групп в порядке появления
        root = {"children": [], "kids": {}}
        for it in sc["items"]:
            if it.get("skip"):
                continue
            node = root
            for g in it.get("groups", []):
                last = node["children"][-1] if node["children"] else None
                if last is not None and isinstance(last, dict) and last.get("g") == g:
                    node = last
                else:
                    newg = {"g": g, "children": []}; node["children"].append(newg); node = newg
            node["children"].append(it)

        def op(it):
            o = it.get("opacity", 1)
            return f' opacity="{fnum(o)}"' if o < 0.999 else ""

        def emit(it):
            i = nid(); names[i] = [it.get("name", "Слой"), bool(it.get("hidden")), round(it.get("opacity", 1), 3) if it["type"] in ("image", "raster", "svg") else 1]
            t = it["type"]
            if t == "rect":
                x, y, w, h = it["x"], it["y"], it["w"], it["h"]
                sw = it.get("stroke")
                out = []
                if it.get("grad"):
                    gid = nid("gr"); g = it["grad"]
                    import math
                    a = math.radians(g["ang"]); dx, dy = math.sin(a), -math.cos(a)
                    stops = "".join(f'<stop offset="{fnum(s["o"])}" stop-color="{"#%02x%02x%02x" % (round(s["c"]["r"]), round(s["c"]["g"]), round(s["c"]["b"]))}" stop-opacity="{fnum(s["c"]["a"])}"/>' for s in g["stops"])
                    defs.append(f'<linearGradient id="{gid}" x1="{fnum(.5 - dx / 2)}" y1="{fnum(.5 - dy / 2)}" x2="{fnum(.5 + dx / 2)}" y2="{fnum(.5 + dy / 2)}">{stops}</linearGradient>')
                    if it.get("fill"):
                        j = nid(); names[j] = [it["name"] + " — цвет", bool(it.get("hidden"))]
                        out.append(f'<rect id="{j}" x="{fnum(x)}" y="{fnum(y)}" width="{fnum(w)}" height="{fnum(h)}" rx="{fnum(it["rx"])}" fill="{it["fill"]["c"]}" fill-opacity="{fnum(it["fill"]["a"])}"{op(it)}/>')
                    fill = f'fill="url(#{gid})"'
                elif it.get("fill"):
                    fill = f'fill="{it["fill"]["c"]}"' + (f' fill-opacity="{fnum(it["fill"]["a"])}"' if it["fill"]["a"] < 1 else "")
                else:
                    fill = 'fill="none"'
                st = ""
                if sw:
                    st = f' stroke="{sw["c"]}" stroke-width="{fnum(sw["w"])}"' + (f' stroke-opacity="{fnum(sw["a"])}"' if sw["a"] < 1 else "")
                    x, y, w, h = x + sw["w"] / 2, y + sw["w"] / 2, max(0.5, w - sw["w"]), max(0.5, h - sw["w"])
                rx = min(it["rx"], w / 2, h / 2)
                if abs(w - h) < 0.6 and rx >= w / 2 - 0.6 and rx > 0:
                    out.append(f'<circle id="{i}" cx="{fnum(x + w / 2)}" cy="{fnum(y + h / 2)}" r="{fnum(w / 2)}" {fill}{st}{op(it)}/>')
                else:
                    out.append(f'<rect id="{i}" x="{fnum(x)}" y="{fnum(y)}" width="{fnum(w)}" height="{fnum(h)}"' + (f' rx="{fnum(rx)}"' if rx > 0 else "") + f' {fill}{st}{op(it)}/>')
                return "".join(out)
            if t == "path":
                s = it["stroke"]
                return f'<path id="{i}" d="{it["d"]}" fill="none" stroke="{s["c"]}" stroke-width="{fnum(s["w"])}"{op(it)}/>'
            if t == "text":
                anchor = {"center": "middle", "right": "end"}.get(it["align"], "start")
                texts[i] = {"c": "\r".join(it["lines"]), "lead": round(it["lead"], 2) if len(it["lines"]) > 1 else 0, "tr": it["tracking"]}
                return (f'<text id="{i}" x="{fnum(it["x"])}" y="{fnum(it["y"])}" font-family="{it["font"]}" font-size="{fnum(it["size"])}" '
                        f'fill="{it["color"]}" text-anchor="{anchor}"{op(it)}>{escape(it["lines"][0])}</text>')
            if t == "image":
                data = load_image(it["src"], it["w"], it["h"], it.get("sepia", 0))
                c = it["clip"]
                need = (c["x"] - it["x"] > 0.5 or c["y"] - it["y"] > 0.5 or (it["x"] + it["w"]) - (c["x"] + c["w"]) > 0.5 or (it["y"] + it["h"]) - (c["y"] + c["h"]) > 0.5 or c["rx"] > 0)
                cp = ""
                if need:
                    cid = i  # имя маски = id изображения
                    defs.append(f'<clipPath id="cp{cid}"><rect x="{fnum(c["x"])}" y="{fnum(c["y"])}" width="{fnum(c["w"])}" height="{fnum(c["h"])}"' + (f' rx="{fnum(c["rx"])}"' if c["rx"] else "") + "/></clipPath>")
                    cp = f' clip-path="url(#cp{cid})"'
                return f'<image id="{i}" x="{fnum(it["x"])}" y="{fnum(it["y"])}" width="{fnum(it["w"])}" height="{fnum(it["h"])}" preserveAspectRatio="none" href="{data}"{cp}/>'
            if t == "raster":
                return f'<image id="{i}" x="{fnum(it["x"])}" y="{fnum(it["y"])}" width="{fnum(it["w"])}" height="{fnum(it["h"])}" preserveAspectRatio="none" href="{it["data"]}"/>'
            if t == "svg":
                vb = it["svg"]["vb"]; sxk, syk = it["w"] / (vb[2] or 1), it["h"] / (vb[3] or 1)
                return f'<g id="{i}" transform="translate({fnum(it["x"] - vb[0] * sxk)} {fnum(it["y"] - vb[1] * syk)}) scale({fnum(sxk)} {fnum(syk)})"{op(it)}>{it["svg"]["inner"]}</g>'
            return ""

        def walk(node):
            out = []
            for ch in node["children"]:
                if "g" in ch and "type" not in ch:
                    gid = nid("g"); names[gid] = [ch["g"], False]
                    out.append(f'<g id="{gid}">' + "".join(walk(ch)) + "</g>")
                else:
                    out.append(emit(ch))
            return out

        bgid = nid(); names[bgid] = ["Фон", False]
        content = "".join(walk(root))
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
               f'<defs>{"".join(defs)}</defs><rect id="{bgid}" x="0" y="0" width="{W}" height="{H}" fill="{sc["bg"]}"/>{content}</svg>')
        return svg, names, texts


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scene',type=Path)
    parser.add_argument('output',type=Path,help='Target SVG path')
    args=parser.parse_args()
    scene=json.loads(args.scene.read_text(encoding='utf8'))
    svg,names,texts=SvgBuilder().to_svg(scene)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(svg,encoding='utf8')
    script=post_script(names,texts)
    args.output.with_suffix('.post.js').write_text(script,encoding='utf8')
    args.output.with_suffix('.layers.json').write_text(json.dumps({'names':names,'texts':texts},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'svg':str(args.output),'script':str(args.output.with_suffix('.post.js')),'named_entries':len(names),'text_layers':len(texts)},ensure_ascii=False))
