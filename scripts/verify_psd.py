"""Inventory real PSD layers and optionally enforce a manifest of expected files."""
import argparse
import json
from collections import Counter
from pathlib import Path
from psd_tools import PSDImage

def inspect(path):
    document=PSDImage.open(path)
    counts=Counter();fonts=set();text_names=[];vector_masks=0;pixel_masks=0;groups=[]
    for layer in document.descendants():
        counts[layer.kind]+=1
        if layer.has_vector_mask():vector_masks+=1
        if layer.has_mask():pixel_masks+=1
        if layer.is_group():groups.append(layer.name)
        if layer.kind=='type':
            text_names.append(layer.name)
            try: fonts.update(str(font['Name']) for font in layer.resource_dict['FontSet'])
            except (KeyError,TypeError,AttributeError):pass
    return {'width':document.width,'height':document.height,'layers':dict(counts),
            'vector_masks':vector_masks,'pixel_masks':pixel_masks,'guides':1032 in document.image_resources,
            'fonts':sorted(fonts),'text_layer_names':text_names,'groups':groups}

def verify(root,expected_count=None,require_text=False,manifest=None):
    files=[root] if root.is_file() else sorted(root.rglob('*.psd'))
    base=root.parent if root.is_file() else root
    errors=[];rows=[];total=Counter()
    expected={row['path']:row for row in (manifest or {}).get('files',[])}
    actual={file.relative_to(base).as_posix() for file in files}
    if not files:errors.append('No PSD files found')
    if expected_count is not None and len(files)!=expected_count:errors.append(f'Expected {expected_count} files, found {len(files)}')
    for missing in sorted(set(expected)-actual):errors.append('Missing PSD: '+missing)
    if manifest is not None:
        for extra in sorted(actual-set(expected)):errors.append('Unlisted PSD: '+extra)
    for file in files:
        name=file.relative_to(base).as_posix()
        try:
            row={'path':name,**inspect(file)};rows.append(row);total.update(row['layers'])
            rules=expected.get(name,{})
            min_text=rules.get('min_text',1 if require_text else 0)
            if row['layers'].get('type',0)<min_text:errors.append(name+': editable text missing')
            if row['layers'].get('shape',0)<rules.get('min_shapes',0):errors.append(name+': vector shapes missing')
            if rules.get('require_guides') and not row['guides']:errors.append(name+': guides missing')
            if rules.get('require_masks') and not(row['vector_masks']+row['pixel_masks']):errors.append(name+': masks missing')
            if 'width' in rules and row['width']!=rules['width']:errors.append(name+': unexpected canvas width')
            if rules.get('required_text_layers'):
                for needed in rules['required_text_layers']:
                    if needed not in row['text_layer_names']:errors.append(name+': missing text layer '+needed)
        except Exception as error:errors.append(name+': '+str(error))
    return {'file_count':len(files),'totals':dict(total),'files':rows,'errors':errors,'ok':not errors}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root',type=Path);parser.add_argument('--expected',type=int)
    parser.add_argument('--require-text',action='store_true');parser.add_argument('--manifest',type=Path)
    parser.add_argument('--json',dest='json_path',type=Path)
    args=parser.parse_args()
    manifest=json.loads(args.manifest.read_text(encoding='utf8')) if args.manifest else None
    report=verify(args.root,args.expected,args.require_text,manifest)
    if args.json_path:
        args.json_path.parent.mkdir(parents=True,exist_ok=True)
        args.json_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    for row in report['files']:print(row['path'],row['layers'],'guides='+str(row['guides']),'masks='+str(row['vector_masks']+row['pixel_masks']))
    for error in report['errors']:print('ERROR:',error)
    print('TOTAL',report['file_count'],report['totals'],'PASS' if report['ok'] else 'FAIL')
    raise SystemExit(0 if report['ok'] else 1)
