"""Add a visible scene-export button to generated HTML; control it with approved browser tools."""
import argparse
import json
from pathlib import Path

def prepare(source,output,fonts=None,width=None):
    if output.parent.resolve()!=source.parent.resolve():raise ValueError('Keep capture HTML beside source HTML so relative assets still resolve')
    scene=(Path(__file__).parent/'scene.js').read_text(encoding='utf8').strip()
    markup=source.read_text(encoding='utf8')
    mapping=json.dumps(fonts or {},ensure_ascii=False)
    injection='''<div data-skip id="__capture_ui" style="position:fixed;right:12px;top:12px;z-index:2147483647;background:#fff;border:1px solid #bbb;padding:8px;font:14px Arial;color:#111"><button id="__capture_button">Экспортировать сцену для PSD</button><span id="__capture_status"></span></div><script>
window.__PSD_FONT_MAP=__FONT_VALUE__;
document.querySelector('#__capture_button').onclick=async function(){
 const button=this,status=document.querySelector('#__capture_status');button.disabled=true;
 try{
  await document.fonts.ready;
  await Promise.all(Array.from(document.images).map(image=>image.decode().catch(()=>null)));
  if(Array.from(document.images).some(image=>!image.complete||!image.naturalWidth))throw new Error('Есть незагруженное изображение');
  const scene=SCENE_CODE;
  scene.width=__CANVAS_WIDTH__ || Math.ceil(document.body.getBoundingClientRect().width);
  if(scene.items.some(item=>item.type==='raster'))throw new Error('Сцена содержит fallback raster: упростите CSS или подготовьте фрагменты отдельно');
  for(const item of scene.items.filter(item=>item.type==='svg')){
   const original=window.__S[item.idx],copy=original.cloneNode(true);
   const originals=[original,...original.querySelectorAll('*')],copies=[copy,...copy.querySelectorAll('*')];
   originals.forEach((element,index)=>{
    const computed=getComputedStyle(element),target=copies[index];
    for(const property of ['fill','stroke','stroke-width','fill-opacity','stroke-opacity','opacity','stroke-dasharray','stroke-linecap','stroke-linejoin']){
     const value=computed.getPropertyValue(property);if(value&&value!=='normal')target.setAttribute(property,value);
    }
    if(element.tagName==='text'){
     const family=computed.fontFamily.split(',')[0].replace(/["']/g,'').trim();
     const key=String(computed.fontWeight)+(computed.fontStyle==='italic'?'italic':'');
     const font=(window.__PSD_FONT_MAP[family]||{})[key]||(family==='Neucha'?'Neucha':family==='Arial'?(+computed.fontWeight>=600?'Arial-BoldMT':'ArialMT'):null);
     if(!font)throw new Error('Добавьте проверенное начертание SVG: '+family+' '+key);
     target.setAttribute('font-family',font);target.setAttribute('font-size',computed.fontSize);target.removeAttribute('font-weight');
    }
    target.removeAttribute('class');target.removeAttribute('style');
   });
   const v=original.viewBox.baseVal;
   item.svg={inner:copy.innerHTML,vb:v.width?[v.x,v.y,v.width,v.height]:[0,0,item.w,item.h]};
  }
  const result=await fetch('/__scene/EXPORT_NAME.scene.json',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(scene)});
  if(!result.ok)throw new Error(await result.text());status.textContent=JSON.stringify(await result.json());
 }catch(error){status.textContent='Ошибка: '+error.message}finally{button.disabled=false}
};</script>'''
    injection=injection.replace('__FONT_VALUE__',mapping.replace('</script','<\\/script'),1).replace('__CANVAS_WIDTH__',json.dumps(width)).replace('SCENE_CODE',scene).replace('EXPORT_NAME',source.stem)
    # Export UI is excluded by data-skip; it is a developer helper, not part of the design.
    if '</body>' in markup:markup=markup.replace('</body>',injection+'</body>',1)
    else:markup+=injection
    output.write_text(markup,encoding='utf8')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('output',type=Path);parser.add_argument('--fonts',type=Path)
    parser.add_argument('--width',type=int,help='Expected canvas width; set browser viewport to the same width')
    args=parser.parse_args()
    if not all(c.isascii() and (c.isalnum() or c in '_.-') for c in args.source.stem):parser.error('Use an ASCII stable page ID for capture filenames')
    if args.source.resolve()==args.output.resolve():parser.error('Capture must be a separate file')
    if args.width is not None and args.width<=0:parser.error('width must be positive')
    prepare(args.source,args.output,json.loads(args.fonts.read_text(encoding='utf8')) if args.fonts else None,args.width)
    print(args.output)
