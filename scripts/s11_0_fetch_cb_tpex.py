#!/usr/bin/env python3
"""
S11-0: TPEx 可轉債公開資料抓取(不需 token)

背景:FinMind 的 TaiwanStockConvertibleBond* 資料集被會員等級擋(免費層
402/400),改用櫃買中心公開 API。經探測(見 results/s11_0_inventory.md):
  - OpenAPI  /openapi/v1/bond_ISSBD5_data   轉(交)換債發行資料(僅存續中 → 有存活者偏誤)
  - Web API  POST /www/zh-tw/bond/{action}  data={'response':'json', ...}
      bond/convSearch     最近上櫃轉(交)換公司債
      bond/convDelist     最近下櫃轉(交)換公司債
      bond/putProvision   賣回權資料(startDate/endDate 西元 yyyy/mm/dd)
      bond/cbCoupon       債息資料
      bond/cbnote         轉(交)換債轉換暨累計彙總表(當月)
      bond/redeem         轉換公司債行使贖回權公告(date=yyyy/mm/dd)
      bond/cbDaily        日統計報表檔案清單(date, fileCode=rsta0113)
  - CSV      /storage/bond_zone/tradeinfo/cb/{yyyy}/{yyyymm}/RSta0113.{yyyymmdd}-C.csv
      每日全市場轉(交)換公司債買賣斷行情(Big5),歷史回到 2007
      → 逐月抽首個交易日重建 PIT 宇宙(含已下櫃債,無存活者偏誤)

用法:
  python scripts/s11_0_fetch_cb_tpex.py static    # 條款/名單類(~1 分鐘)
  python scripts/s11_0_fetch_cb_tpex.py monthly   # 逐月首交易日行情 2007-01~今(可續跑)
  python scripts/s11_0_fetch_cb_tpex.py universe  # 解析 monthly CSV → cb_universe.parquet

鐵律:單線程、REQ_INTERVAL 0.8s(TPEx 公開站,禮貌性限流)、可續跑。
"""
import io
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CB_DIR = ROOT / 'data' / 'cb'
MONTHLY_DIR = CB_DIR / 'tpex_monthly'
CB_DIR.mkdir(parents=True, exist_ok=True)
MONTHLY_DIR.mkdir(parents=True, exist_ok=True)

BASE = 'https://www.tpex.org.tw'
HEADERS = {'User-Agent': 'Mozilla/5.0', 'Referer': BASE + '/zh-tw/'}
REQ_INTERVAL = 0.8
_last = [0.0]

SES = requests.Session()
SES.headers.update(HEADERS)


def _throttle():
    wait = REQ_INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()


def get(url, retries=3, **kw):
    for attempt in range(retries):
        _throttle()
        try:
            r = SES.get(url, timeout=60, **kw)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as e:
            print(f'  GET 失敗 {attempt+1}/{retries}: {e},睡 15s')
            time.sleep(15)
    raise RuntimeError(f'GET {url} 重試失敗')


def post_json(action, retries=3, **data):
    payload = {'response': 'json', **data}
    for attempt in range(retries):
        _throttle()
        try:
            r = SES.post(f'{BASE}/www/zh-tw/{action}', data=payload, timeout=60)
            r.raise_for_status()
            j = r.json()
            if j.get('stat') != 'ok':
                raise RuntimeError(f'{action} stat={j.get("stat")}')
            return j
        except (requests.exceptions.RequestException, ValueError) as e:
            print(f'  POST {action} 失敗 {attempt+1}/{retries}: {e},睡 15s')
            time.sleep(15)
    raise RuntimeError(f'POST {action} 重試失敗')


def tables_to_df(j, idx=0):
    t = j['tables'][idx]
    return pd.DataFrame(t.get('data', []), columns=t.get('fields'))


def roc_to_ad(s):
    """'102/01/31' → '2013-01-31';容錯空值。"""
    m = re.match(r'(\d{2,3})/(\d{2})/(\d{2})', str(s).strip())
    if not m:
        return None
    return f'{int(m.group(1)) + 1911:04d}-{m.group(2)}-{m.group(3)}'


# ---------------------------------------------------------------- static
def fetch_static():
    # 1) OpenAPI 發行資料(存續中全部,含轉換價/發行日/賣回日)
    r = get(f'{BASE}/openapi/v1/bond_ISSBD5_data')
    info = pd.DataFrame(r.json())
    info.to_parquet(CB_DIR / 'cb_info_issbd5.parquet')
    print(f'ISSBD5 發行資料: {len(info)} 列 → cb_info_issbd5.parquet')

    # 2) 最近上櫃 / 下櫃
    for action, fn in [('bond/convSearch', 'cb_recent_listed'),
                       ('bond/convDelist', 'cb_recent_delisted')]:
        df = tables_to_df(post_json(action))
        df.to_parquet(CB_DIR / f'{fn}.parquet')
        print(f'{action}: {len(df)} 列 → {fn}.parquet')

    # 3) 賣回權資料:逐年抓(startDate/endDate 西元)
    puts = []
    for y in range(2007, 2029):
        j = post_json('bond/putProvision',
                      startDate=f'{y}/01/01', endDate=f'{y}/12/31')
        df = tables_to_df(j)
        if len(df):
            puts.append(df)
        print(f'putProvision {y}: {len(df)} 列')
    if puts:
        allp = pd.concat(puts, ignore_index=True).drop_duplicates()
        allp.to_parquet(CB_DIR / 'cb_put_provision.parquet')
        print(f'賣回權合計 {len(allp)} 列 → cb_put_provision.parquet')

    # 4) 債息 + 轉換彙總(當月)
    for action, fn in [('bond/cbCoupon', 'cb_coupon'),
                       ('bond/cbnote', 'cb_conversion_note')]:
        try:
            df = tables_to_df(post_json(action))
            df.to_parquet(CB_DIR / f'{fn}.parquet')
            print(f'{action}: {len(df)} 列 → {fn}.parquet')
        except Exception as e:
            print(f'{action} 失敗(非致命): {e}')


# ---------------------------------------------------------------- monthly
def list_month_files(y, m):
    """cbDaily 回傳該月所有 RSta0113 檔案清單 [(roc_date, url), ...]。"""
    j = post_json('bond/cbDaily', date=f'{y}/{m:02d}/15', fileCode='rsta0113')
    rows = j['tables'][0].get('data', []) if j.get('tables') else []
    out = []
    for d, u in rows:
        ad = roc_to_ad(d)
        if ad and ad[:7] == f'{y}-{m:02d}':
            out.append((ad, u))
    return sorted(out)


def fetch_monthly():
    status_p = CB_DIR / 'monthly_status.json'
    status = json.loads(status_p.read_text()) if status_p.exists() else {}
    today = pd.Timestamp.today()
    months = pd.period_range('2007-01', today.strftime('%Y-%m'), freq='M')
    todo = [p for p in months if str(p) not in status]
    print(f'待抓 {len(todo)} / {len(months)} 個月(續跑自動跳過)')
    for k, p in enumerate(todo):
        key = str(p)
        try:
            files = list_month_files(p.year, p.month)
            if not files:
                status[key] = 'no_data'
            else:
                ad, url = files[0]          # 該月首個交易日
                r = get(BASE + url)
                out = MONTHLY_DIR / Path(url).name
                out.write_bytes(r.content)
                status[key] = ad
        except Exception as e:
            print(f'{key} 失敗(下輪重試): {e}')
            continue
        status_p.write_text(json.dumps(status))
        if (k + 1) % 24 == 0:
            print(f'進度 {k+1}/{len(todo)}({key})')
    done = sum(1 for v in status.values() if v != 'no_data')
    print(f'本輪結束:有檔 {done} 個月 / 無資料 {len(status)-done} 個月')


# ---------------------------------------------------------------- universe
def parse_rsta0113(path):
    """解析單日行情 CSV(Big5)→ DataFrame。等價/議價兩列一組,取等價列。"""
    raw = path.read_bytes().decode('big5', errors='replace')
    date = None
    rows = []
    cur = None
    for line in raw.splitlines():
        cells = next(iter(pd.read_csv(io.StringIO(line), header=None,
                                      dtype=str, keep_default_na=False)
                          .itertuples(index=False)), None)
        if cells is None:
            continue
        cells = list(cells)
        tag = cells[0]
        if tag == 'DATADATE':
            m = re.search(r'(\d{2,3})年(\d{2})月(\d{2})日', cells[1])
            if m:
                date = f'{int(m.group(1))+1911:04d}-{m.group(2)}-{m.group(3)}'
        elif tag == 'BODY':
            body = cells[1:]
            code = body[0].strip()
            if re.fullmatch(r'\d{5,6}', code):   # 等價列(帶代號;排除合計列)
                cur = body
                rows.append(body)
            elif cur is not None:
                pass                      # 議價列,先不用
    cols = ['code', 'name', 'session', 'close', 'chg', 'open', 'high', 'low',
            'n_trades', 'units', 'amount', 'avg_price', 'ref_price_next',
            'limit_up_next', 'limit_dn_next']
    df = pd.DataFrame(rows, columns=cols[:len(rows[0])] if rows else cols)
    df['date'] = date
    return df


def build_universe():
    files = sorted(MONTHLY_DIR.glob('RSta0113.*.csv'))
    print(f'解析 {len(files)} 個月檔...')
    frames = []
    for f in files:
        try:
            frames.append(parse_rsta0113(f))
        except Exception as e:
            print(f'  {f.name} 解析失敗: {e}')
    panel = pd.concat(frames, ignore_index=True)
    for c in ['close', 'open', 'high', 'low', 'avg_price', 'ref_price_next']:
        panel[c] = pd.to_numeric(panel[c].str.replace(',', '').str.strip(),
                                 errors='coerce')
    panel['units'] = pd.to_numeric(panel['units'].str.replace(',', ''),
                                   errors='coerce')
    panel['amount'] = pd.to_numeric(panel['amount'].str.replace(',', ''),
                                    errors='coerce')
    panel['name'] = panel['name'].str.strip()
    panel.to_parquet(CB_DIR / 'cb_universe_monthly.parquet')

    g = panel.groupby('code')
    summary = pd.DataFrame({
        'name': g['name'].last(),
        'first_seen': g['date'].min(),
        'last_seen': g['date'].max(),
        'n_months': g['date'].nunique(),
    }).reset_index()
    summary.to_parquet(CB_DIR / 'cb_universe_summary.parquet')
    print(f'宇宙:{panel["code"].nunique()} 檔債券,{len(panel)} 債·月列')
    print(f'→ cb_universe_monthly.parquet / cb_universe_summary.parquet')


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'static'
    {'static': fetch_static, 'monthly': fetch_monthly,
     'universe': build_universe}[mode]()
