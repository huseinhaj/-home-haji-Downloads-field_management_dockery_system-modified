#!/usr/bin/env python3
"""
Scrape HFR Portal (hfrportal.moh.go.tz) — orodha KAMILI ya vituo vya afya Tanzania.
Chanzo: https://hfrportal.moh.go.tz/web/index.php?r=portal/quick-search&filters=ALLs
"""
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = 'https://hfrportal.moh.go.tz/web/index.php'
HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
           'Accept-Language': 'en-US,en;q=0.9'}

def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode('utf-8', 'ignore')
        except Exception as e:
            print(f'  retry {i+1}: {e}', file=sys.stderr)
            time.sleep(2)
    return ''

def parse_page(html):
    """Extract facility rows from gridview HTML."""
    rows = []
    # each row: <tr> with td.w1 data-col-seq="1..8"
    tr_pat = re.compile(r'<tr[^>]*>(.*?)</tr>', re.S)
    td_pat = re.compile(r'<td[^>]*data-col-seq="(\d+)"[^>]*>(.*?)</td>', re.S)
    for tr in tr_pat.findall(html):
        cells = {}
        for seq, content in td_pat.findall(tr):
            text = re.sub(r'<[^>]+>', ' ', content)
            text = re.sub(r'\s+', ' ', text).strip()
            cells[int(seq)] = text
        if 1 in cells and cells[1]:
            rows.append({
                'code': cells.get(1, ''),
                'name': cells.get(2, ''),
                'type': cells.get(3, ''),
                'region': cells.get(4, '').replace(' Region', '').strip(),
                'council': cells.get(5, ''),
                'ownership_category': cells.get(6, ''),
                'ownership_authority': cells.get(7, ''),
                'status': cells.get(8, ''),
            })
    return rows

def main():
    out_csv = '/tmp/health_data/hfr_facilities.csv'
    out_json = '/tmp/health_data/hfr_facilities.json'
    start_page = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    end_page = int(sys.argv[2]) if len(sys.argv) > 2 else 713

    all_rows = []
    # resume support
    if start_page > 1:
        try:
            all_rows = json.load(open('/tmp/health_data/hfr_partial.json'))
        except Exception:
            pass

    for page in range(start_page, end_page + 1):
        url = f'{BASE}?r=portal%2Fquick-search&filters=ALLs&page={page}'
        html = fetch(url)
        rows = parse_page(html)
        if not rows:
            print(f'page {page}: EMPTY, stopping', file=sys.stderr)
            break
        all_rows.extend(rows)
        if page % 25 == 0 or page == start_page:
            print(f'page {page}/{end_page}: total {len(all_rows)}', flush=True)
            json.dump(all_rows, open('/tmp/health_data/hfr_partial.json', 'w'))
        time.sleep(0.25)

    # write final
    with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=['code', 'name', 'type', 'region', 'council', 'ownership_category', 'ownership_authority', 'status'])
        w.writeheader()
        w.writerows(all_rows)
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(all_rows, f, ensure_ascii=False, indent=1)
    print(f'DONE: {len(all_rows)} facilities -> {out_csv}')

if __name__ == '__main__':
    main()
