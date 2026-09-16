#!/usr/bin/env python3
"""
Sahishi Bridge — programu ndogo inayokaa PC ya shule (Ubuntu).
Inaunganisha scanner ya ADF moja kwa moja na site ya Sahishi.

Matumizi:
  # 1. Thibitisha token (Server inatoa token kwa admin)
  python3 bridge.py --ping

  # 2. Anza kusikiliza kazi (run loop — weka kwenye systemd)
  python3 bridge.py --serve

  # 3. Ona scanner zilizopo
  python3 bridge.py --scanners

  # 4. Jaribu scan moja (bila kutuma)
  python3 bridge.py --test-scan

Config (env au file .env karibu na bridge.py):
  SAHISHI_SERVER=https://your-site.up.railway.app
  SAHISHI_TOKEN=sb_xxxxxxxxxxxx
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent

# Config: env vars zina kipaumbele, kisha .env file
def _load_env_file():
    env_file = BASE_DIR / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

_load_env_file()

SERVER = (os.environ.get('SAHISHI_SERVER') or '').rstrip('/')
TOKEN = os.environ.get('SAHISHI_TOKEN') or ''
SCAN_DIR = Path(os.environ.get('SAHISHI_SCAN_DIR') or (BASE_DIR / 'scans'))

HEADERS = {'Authorization': f'Bearer {TOKEN}'}


def api(path):
    return f'{SERVER}/shule/sahishi/bridge/api/{path}'


def ping():
    r = requests.get(api('ping/'), headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    print(f"✓ Server: {SERVER}")
    print(f"  Bridge: {data.get('bridge')}")
    print(f"  Scanner iliyohifadhiwa: {data.get('scanner') or '(haijawekwa)'}")
    return data


def list_scanners():
    out = subprocess.run(['scanimage', '-L'], capture_output=True, text=True, timeout=60)
    devices = []
    for line in (out.stdout or '').splitlines():
        if line.startswith('device `'):
            name = line.split('`')[1].split("'")[0]
            label = line.split('is a ', 1)[-1].strip()
            devices.append((name, label))
    return devices


def scan_adf(device, pages, duplex, dpi, job_id):
    """Scan ADF → folder ya job. Inarudi list ya file paths."""
    out_dir = SCAN_DIR / f'job_{job_id}'
    out_dir.mkdir(parents=True, exist_ok=True)
    # Futa scans za zamani za job hii
    for old in out_dir.glob('scan_*.png'):
        old.unlink()

    prefix = str(out_dir / 'scan')
    cmd = [
        'scanimage', '-d', device,
        '--format=png',
        f'--batch={prefix}_%04d.png',
        f'--batch-count={pages}',
        f'--resolution={dpi}',
        '--mode=Color',
        '--source=ADF Duplex' if duplex else '--source=ADF',
    ]
    print(f'  Scan: {" ".join(cmd[:4])} ... pages={pages} duplex={duplex} dpi={dpi}')
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    files = sorted(out_dir.glob('scan_*.png'))
    if proc.returncode != 0 and not files:
        raise RuntimeError(f'scanimage ilishindikana: {proc.stderr.strip()[:300]}')
    return files


def upload_images(job_id, files):
    files_payload = [
        ('images', (f.name, open(f, 'rb'), 'image/png')) for f in files
    ]
    r = requests.post(
        api(f'upload/{job_id}/'), headers=HEADERS,
        files=files_payload, data={'pages_done': len(files)}, timeout=600,
    )
    r.raise_for_status()
    return r.json()


def report_failure(job_id, reason):
    try:
        requests.post(
            api(f'fail/{job_id}/'), headers=HEADERS,
            data={'reason': reason}, timeout=30,
        )
    except Exception as e:
        print(f'  ⚠ Imeshindikana kuripoti kushindwa: {e}')


def claim_job():
    r = requests.post(api('claim/'), headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json().get('job')


def do_job(job):
    device_env = os.environ.get('SAHISHI_SCANNER', '')
    device = device_env or None
    if not device:
        devices = list_scanners()
        if not devices:
            raise RuntimeError('Hakuna scanner (scanimage -L haina device)')
        device = devices[0][0]

    print(f'  Scanner: {device}')
    files = scan_adf(device, job['pages'], job['duplex'], job['dpi'], job['id'])
    if not files:
        raise RuntimeError('ADF haikutoa kurasa yoyote — angalia karatasi')

    print(f'  Kurasa {len(files)} zimescan. Zinatuma...')
    result = upload_images(job['id'], files)
    print(f"  ✓ {result.get('total')} picha: {result.get('graded')} graded, {result.get('review')} review")
    print(f"  → Fungua review: {SERVER}/shule/exam/{job['exam_id']}/subject/{job['subject_id']}/sahishi/review/")

    # Safisha files za job hii (acha directory tupu)
    for f in files:
        f.unlink(missing_ok=True)


def serve(poll_seconds=4):
    print(f'Bridge inaendelea... (server: {SERVER})')
    print('Bonyeza Ctrl+C kuacha.')
    while True:
        try:
            job = claim_job()
            if job:
                print(f'\n📄 Kazi mpya #{job["id"]}: {job["exam_name"]} — {job["subject_name"]}')
                try:
                    do_job(job)
                except Exception as e:
                    print(f'  ✗ Imeshindikana: {e}')
                    report_failure(job['id'], str(e)[:250])
        except requests.RequestException as e:
            print(f'⚠ Mtandao: {e} (itatinga tena)')
        except KeyboardInterrupt:
            print('\nBye!')
            sys.exit(0)
        time.sleep(poll_seconds)


def main():
    if not SERVER or not TOKEN:
        print('✗ Weka SAHISHI_SERVER na SAHISHI_TOKEN (env au .env file)')
        print('  Mfano:')
        print('    SAHISHI_SERVER=https://your-site.up.railway.app')
        print('    SAHISHI_TOKEN=sb_xxxxxxxx')
        sys.exit(1)

    import argparse
    p = argparse.ArgumentParser(description='Sahishi Bridge')
    p.add_argument('--ping', action='store_true', help='Thibitisha token + server')
    p.add_argument('--serve', action='store_true', help='Endelea kupokea kazi')
    p.add_argument('--scanners', action='store_true', help='Orodha ya scanner')
    p.add_argument('--test-scan', action='store_true', help='Jaribu kurasa 1 (bila kutuma)')
    p.add_argument('--status', action='store_true', help='Ona hali (ping + scanners)')
    args = p.parse_args()

    if args.ping or args.status:
        ping()
    if args.scanners or args.status:
        print('\nScanner zilizopo:')
        for name, label in list_scanners():
            print(f'  {name}\n    → {label}')
    if args.test_scan:
        devices = list_scanners()
        if not devices:
            print('✗ Hakuna scanner')
            sys.exit(1)
        files = scan_adf(devices[0][0], 1, False, 200, 'test')
        print(f'✓ Test scan: {len(files)} file(s) kwenye {SCAN_DIR / "job_test"}')
    if args.serve:
        serve()
    if not any([args.ping, args.serve, args.scanners, args.test_scan, args.status]):
        p.print_help()


if __name__ == '__main__':
    main()
