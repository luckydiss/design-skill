"""Compare HTML and Photopea PNGs without hiding geometry differences by resizing."""
import argparse
import json
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageStat

def compare(first,second,output,slice_height=1600):
    a=Image.open(first).convert('RGB');b=Image.open(second).convert('RGB')
    output.mkdir(parents=True,exist_ok=True)
    same=a.size==b.size
    metrics={'first_size':a.size,'second_size':b.size,'same_size':same}
    if same:
        difference=ImageChops.difference(a,b)
        metrics.update(mean_absolute_error=sum(ImageStat.Stat(difference).mean)/3,
                       changed_pixels=sum(1 for p in difference.getdata() if max(p)>12),
                       max_difference=max(v for extrema in difference.getextrema() for v in extrema))
    width=max(a.width,b.width);height=max(a.height,b.height)
    for top in range(0,height,slice_height):
        bottom=min(height,top+slice_height);canvas=Image.new('RGB',(width*2+24,bottom-top+32),'#dedede')
        draw=ImageDraw.Draw(canvas);draw.text((8,8),'HTML / browser',fill='black');draw.text((width+32,8),'Photopea',fill='black')
        for index,im in enumerate((a,b)):
            if top<im.height:canvas.paste(im.crop((0,top,im.width,min(bottom,im.height))),(index*(width+24),32))
        canvas.save(output/f'compare-{top:05d}.png')
    (output/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf8')
    return metrics

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('browser',type=Path);parser.add_argument('photopea',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--slice-height',type=int,default=1600)
    args=parser.parse_args()
    if args.slice_height<=0:parser.error('slice-height must be positive')
    result=compare(args.browser,args.photopea,args.output,args.slice_height)
    print(json.dumps(result))
    raise SystemExit(0 if result['same_size'] else 1)
