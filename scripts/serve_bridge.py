"""Serve a local Photopea bridge and store generated exports in a chosen task folder."""
import argparse
import json
import re
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

def make_handler(root,output):
    assets=Path(__file__).resolve().parent.parent/'assets'
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(root),**kwargs)
        def translate_path(self,path):
            relative=unquote(urlsplit(path).path).lstrip('/')
            target=(root/relative).resolve()
            if not target.is_relative_to(root):return str(root/'__invalid_path__')
            return str(target)
        def do_GET(self):
            if urlsplit(self.path).path=='/__photopea_bridge':
                data=(assets/'photopea-bridge.html').read_bytes()
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
            else:super().do_GET()
        def do_POST(self):
            if urlsplit(self.path).path.startswith('/__scene/'):
                name=unquote(urlsplit(self.path).path.removeprefix('/__scene/'))
                if not re.fullmatch(r'[A-Za-z0-9_.-]+\.scene\.json',name):self.send_error(400,'Invalid scene name');return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=100*1024*1024:raise ValueError('Invalid scene payload size')
                    scene=json.loads(self.rfile.read(size))
                    if not isinstance(scene,dict) or not isinstance(scene.get('items'),list) or not all(isinstance(scene.get(k),(int,float)) and scene[k]>0 for k in ('width','height')):raise ValueError('Invalid scene structure')
                    for item in scene['items']:
                        if item.get('type')=='image' and item.get('src','').startswith(('http:','https:')):
                            url=urlsplit(item['src'])
                            if url.netloc==self.headers.get('Host'):
                                local=(root/unquote(url.path).lstrip('/')).resolve()
                                if not local.is_relative_to(root) or not local.is_file():raise ValueError('Image outside served project or missing')
                                item['src']=str(local)
                    output.mkdir(parents=True,exist_ok=True);target=output/name
                    target.write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf8')
                    response=json.dumps({'saved':str(target),'items':len(scene['items'])}).encode()
                    self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(response)));self.end_headers();self.wfile.write(response)
                except (ValueError,TypeError,KeyError) as error:self.send_error(400,str(error))
                return
            name=unquote(urlsplit(self.path).path.removeprefix('/__save/'))
            if not self.path.startswith('/__save/') or not re.fullmatch(r'[A-Za-z0-9_.-]+\.(psd|png)',name):self.send_error(400,'Invalid export name');return
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=1024*1024*1024:self.send_error(413,'Invalid payload size');return
            data=self.rfile.read(size)
            if len(data)!=size:self.send_error(400,'Incomplete payload');return
            if name.endswith('.psd') and not data.startswith(b'8BPS'):self.send_error(400,'Not a PSD');return
            if name.endswith('.png') and not data.startswith(b'\x89PNG\r\n\x1a\n'):self.send_error(400,'Not a PNG');return
            target=output/name
            # Explicit write target; the server never chooses unrelated file paths.
            output.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            response=json.dumps({'saved':str(target),'bytes':size}).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(response)));self.end_headers();self.wfile.write(response)
    return Handler

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args();root=args.root.resolve();output=args.output.resolve()
    if not root.is_dir():parser.error('root directory does not exist')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(root,output))
    print(f'http://127.0.0.1:{server.server_port}/__photopea_bridge',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
