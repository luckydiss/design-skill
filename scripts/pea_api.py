"""Управление Photopea через API (iframe + postMessage): запуск скриптов, загрузка файлов, сохранение PSD."""
import base64
import json
import time
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright

CFG = {"environment": {"lang": "ru", "theme": 2, "intro": False}}
PP_URL = "https://www.photopea.com#" + urllib.parse.quote(json.dumps(CFG))

HOST = f"""<!doctype html><html><body style="margin:0;background:#222">
<iframe id="pp" src="{PP_URL}" style="border:0;width:100vw;height:100vh"></iframe>
<script>
window.__msgs = [];
window.addEventListener('message', e => {{
  if (e.source !== document.getElementById('pp').contentWindow || e.origin !== 'https://www.photopea.com') return;
  if (e.data instanceof ArrayBuffer) {{
    const u = new Uint8Array(e.data); let s = ''; const CH = 0x8000;
    for (let i = 0; i < u.length; i += CH) s += String.fromCharCode.apply(null, u.subarray(i, i + CH));
    window.__msgs.push({{bin: btoa(s)}});
  }} else window.__msgs.push({{txt: e.data}});
}});
window.__send = (m) => document.getElementById('pp').contentWindow.postMessage(m, 'https://www.photopea.com');
window.__sendBin = (b64) => {{ const s = atob(b64); const u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); document.getElementById('pp').contentWindow.postMessage(u.buffer, 'https://www.photopea.com'); }};
</script></body></html>"""


class PeaAPI:
    def __init__(self, w=1700, h=1000, headless=True):
        self.p = sync_playwright().start()
        self.b = self.p.chromium.launch(channel="chrome", headless=headless)
        self.pg = self.b.new_page(viewport={"width": w, "height": h})
        self.pg.route("http://local.host/", lambda r: r.fulfill(body=HOST, content_type="text/html"))
        self.pg.goto("http://local.host/")
        self._wait_done(timeout=90)  # Photopea шлёт "done" после загрузки

    def _wait_done(self, timeout=120):
        t0 = time.time(); out = []
        while time.time() - t0 < timeout:
            msgs = self.pg.evaluate("() => window.__msgs.splice(0)")
            for m in msgs:
                if m.get("txt") == "done":
                    return out
                out.append(m)
            time.sleep(0.15)
        raise TimeoutError("Photopea did not answer 'done'")

    def run(self, script, timeout=300):
        """Выполнить скрипт; вернуть список сообщений (echoToOE строки и бинарные файлы)."""
        self.pg.evaluate("(s) => window.__send(s)", script)
        msgs = self._wait_done(timeout)
        res = []
        for m in msgs:
            res.append(base64.b64decode(m["bin"]) if "bin" in m else m["txt"])
        return res

    def open_bytes(self, data: bytes, timeout=120):
        self.pg.evaluate("(b) => window.__sendBin(b)", base64.b64encode(data).decode())
        return self._wait_done(timeout)

    def shot(self, path, clip=None):
        self.pg.screenshot(path=str(path), clip=clip)

    def close(self):
        self.b.close(); self.p.stop()
