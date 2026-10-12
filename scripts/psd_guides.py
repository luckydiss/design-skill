"""Add grid guides to a PSD record without rasterizing its layers."""
import argparse
import io
import struct
from pathlib import Path

def column_guides(width=1440, container=1170, cols=12, col=None, gutter=30):
    if cols<1 or container<=0 or width<container or gutter<0:
        raise ValueError('Invalid grid dimensions')
    calculated=(container-(cols-1)*gutter)/cols
    if calculated<=0 or (col is not None and abs(col-calculated)>0.01):
        raise ValueError('Column width does not match container and gutter')
    left=(width-container)/2
    return [(left+i*(calculated+gutter)+offset,'v') for i in range(cols) for offset in (0,calculated)]

def add_guides(record,guides):
    from psd_tools.psd.image_resources import ImageResource
    data=struct.pack('>IIII',1,576,576,len(guides))
    for position,direction in guides:
        if direction not in ('v','h'): raise ValueError('Guide direction must be v or h')
        data+=struct.pack('>iB',int(round(position*32)),0 if direction=='v' else 1)
    record.image_resources[1032]=ImageResource(signature=b'8BIM',key=1032,name='',data=data)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    parser.add_argument('--width',type=int,default=1440);parser.add_argument('--container',type=float,default=1170)
    parser.add_argument('--columns',type=int,default=12);parser.add_argument('--gutter',type=float,default=30)
    args=parser.parse_args()
    from psd_tools import PSDImage
    document=PSDImage.open(args.input)
    if document.width!=args.width: raise ValueError('PSD width differs from configured grid')
    add_guides(document._record,column_guides(args.width,args.container,args.columns,gutter=args.gutter))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    buffer=io.BytesIO();document._record.write(buffer);args.output.write_bytes(buffer.getvalue())
    print(args.output)
