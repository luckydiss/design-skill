"""Build selected design sheets from a project manifest using the Photopea API runner.

Run only where standalone Playwright is allowed. Manifest paths are relative to
the manifest directory; jobs may share HTML and vary pre_js / pre_arg.
"""
import argparse
import json
from pathlib import Path


def load_jobs(manifest, selected=()):
    manifest = Path(manifest).resolve()
    data = json.loads(manifest.read_text(encoding='utf-8'))
    base = manifest.parent
    jobs = data.get('jobs', [])
    if not jobs:
        raise ValueError('Manifest must contain jobs')
    ids, outputs, normalized = set(), set(), []
    for raw in jobs:
        job = dict(raw)
        identity = job['id']
        if not isinstance(identity, str) or not identity or identity in ids:
            raise ValueError(f'Invalid or duplicate job id: {identity!r}')
        ids.add(identity)
        for field in ('html', 'psd', 'pre_js', 'fonts'):
            if job.get(field):
                job[field] = (base / job[field]).resolve()
        if 'html' not in job or 'psd' not in job:
            raise ValueError(f'{identity}: html and psd are required')
        if job['psd'].suffix.lower() != '.psd':
            raise ValueError(f'{identity}: output must be .psd')
        job['png'] = job['psd'].with_suffix('.png')
        job['browser'] = job['psd'].with_name(job['psd'].stem + '_browser.png')
        for path in (job['psd'], job['png'], job['browser']):
            key = str(path).casefold()
            if key in outputs:
                raise ValueError(f'Colliding job output: {path}')
            outputs.add(key)
        for field in ('html', 'pre_js', 'fonts'):
            if job.get(field) and not job[field].is_file():
                raise ValueError(f'{identity}: missing {field}: {job[field]}')
        if job.get('width', 1440) <= 0:
            raise ValueError(f'{identity}: width must be positive')
        normalized.append(job)
    unknown = set(selected) - ids
    if unknown:
        raise ValueError(f'Unknown job ids: {sorted(unknown)}')
    return [j for j in normalized if not selected or j['id'] in selected]


def run_jobs(jobs, report_path, restart_every=8, builder_factory=None, grid_factory=None):
    if restart_every < 1:
        raise ValueError('restart_every must be positive')
    if builder_factory is None:
        from build_pea import Builder
        builder_factory = Builder
    if grid_factory is None:
        from psd_guides import column_guides
        grid_factory = column_guides
    results, builder, used = [], None, 0
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        for job in jobs:
            try:
                if builder is None:
                    builder = builder_factory()
                builder.font_map = json.loads(job['fonts'].read_text(encoding='utf-8')) if job.get('fonts') else {}
                width = job.get('width', 1440)
                grid = job.get('grid')
                guides = grid_factory(width, grid['container'], grid.get('columns', 12), gutter=grid.get('gutter', 30)) if grid else None
                job['psd'].parent.mkdir(parents=True, exist_ok=True)
                builder.build(job['html'], job['psd'], job['png'], width=width,
                              pre_js=job['pre_js'].read_text(encoding='utf-8') if job.get('pre_js') else None,
                              pre_arg=job.get('pre_arg'), guides=guides, flat_png=job['browser'])
                for field in ('psd', 'png', 'browser'):
                    if not job[field].is_file() or job[field].stat().st_size == 0:
                        raise RuntimeError(f'Missing or empty output: {job[field]}')
                results.append({'id': job['id'], 'status': 'built', 'psd': str(job['psd'])})
                used += 1
            except Exception as error:
                results.append({'id': job['id'], 'status': 'failed', 'error': str(error)})
                if builder is not None:
                    builder.close()
                    builder = None
                used = 0
            report_path.write_text(json.dumps({'jobs': results}, ensure_ascii=False, indent=2), encoding='utf-8')
            if builder is not None and used >= restart_every:
                builder.close()
                builder, used = None, 0
    finally:
        if builder is not None:
            builder.close()
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--only', nargs='+', default=[])
    parser.add_argument('--report', type=Path)
    parser.add_argument('--restart-every', type=int, default=8)
    args = parser.parse_args()
    jobs = load_jobs(args.manifest, args.only)
    report = args.report or args.manifest.with_suffix('.build-results.json')
    results = run_jobs(jobs, report, args.restart_every)
    failures = [r for r in results if r['status'] == 'failed']
    print(json.dumps({'built': len(results) - len(failures), 'failed': len(failures), 'report': str(report)}, ensure_ascii=False))
    raise SystemExit(1 if failures else 0)
