#!/usr/bin/env python3
"""
S11-A 前置:抓 CB 發行人正股日價 + TAIEX 基準(FinMind 匿名)

實測:FinMind 匿名(無 token)可抓 TaiwanStockPrice / TaiwanStockInfo,
但 CB 專屬資料集被會員等級擋。匿名有小時額度 → REQ_INTERVAL 6.1s,
402/429 睡 600s,status.json 可續跑(鐵律 #1)。

發行人清單來源:
  - cb_universe_summary.parquet(逐月 PIT 宇宙,含已下櫃債)→ code[:4]
  - cb_info_issbd5.parquet 的 IssuerCode 交叉驗證

用法:python scripts/s11_a_fetch_stocks.py
輸出:data/stock/price_{stock_id}.parquet、price_TAIEX.parquet
"""
import json
import sys
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
CB_DIR = ROOT / 'data' / 'cb'
ST_DIR = ROOT / 'data' / 'stock'
ST_DIR.mkdir(parents=True, exist_ok=True)

API = 'https://api.finmindtrade.com/api/v4/data'
REQ_INTERVAL = 6.1
START_DATE = '2012-01-01'   # 事件分析 2013 起,留一年暖身
_last = [0.0]


def api_get(dataset, data_id, retries=5):
    for attempt in range(retries):
        wait = REQ_INTERVAL - (time.time() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(API, params={
                'dataset': dataset, 'data_id': data_id,
                'start_date': START_DATE}, timeout=60)
            _last[0] = time.time()
            if r.status_code in (400, 402, 429):
                msg = ''
                try:
                    msg = r.json().get('msg', '')
                except ValueError:
                    pass
                if 'level' in msg or r.status_code in (402, 429):
                    print(f'  限流({r.status_code} {msg[:40]}),睡 600s')
                    time.sleep(600)
                    continue
            r.raise_for_status()
            j = r.json()
            return pd.DataFrame(j.get('data', []))
        except requests.exceptions.RequestException as e:
            print(f'  {data_id}{attempt+1} 次失敗: {e},睡 30s')
            time.sleep(30)
    raise RuntimeError(f'{data_id} 重試失敗')


def _bond_to_stock(codes):
    """轉(交)換債代號 = 發行人股票代號(4 碼)+ 流水尾碼(1–2 碼)。"""
    codes = codes.astype(str).str.strip()
    return set(codes[codes.str.fullmatch(r'\d{5,6}')].str[:4])


def issuer_list():
    issuers = set()
    p = CB_DIR / 'cb_universe_summary.parquet'
    if p.exists():
        summ = pd.read_parquet(p)
        # 事件分析從 2013 起 → 只抓 2012-12 之後仍在宇宙中的債之發行人
        summ = summ[summ['last_seen'] >= '2012-12-01']
        issuers |= _bond_to_stock(summ['code'])
    else:
        print('cb_universe_summary 尚未生成,先用靜態名單(可續跑補齊)')
    info = pd.read_parquet(CB_DIR / 'cb_info_issbd5.parquet')
    extra = info.loc[info['BondCode'].str.strip().ne(''), 'IssuerCode']
    extra = extra.astype(str).str.strip()
    issuers |= set(extra[extra.str.fullmatch(r'\d{4}')])
    for fn, col in [('cb_recent_listed.parquet', '發行機構代碼'),
                    ('cb_recent_delisted.parquet', '代碼'),
                    ('cb_put_provision.parquet', '代號')]:
        fp = CB_DIR / fn
        if fp.exists():
            s = pd.read_parquet(fp)[col]
            if col == '發行機構代碼':
                s = s.astype(str).str.strip()
                issuers |= set(s[s.str.fullmatch(r'\d{4}')])
            else:
                issuers |= _bond_to_stock(s)
    return sorted(issuers)


def main():
    issuers = issuer_list()
    targets = ['TAIEX'] + issuers
    status_p = ST_DIR / 'status.json'
    status = json.loads(status_p.read_text()) if status_p.exists() else {}
    todo = [s for s in targets if s not in status]
    print(f'待抓 {len(todo)} / {len(targets)}(續跑自動跳過)')
    t0 = time.time()
    for k, sid in enumerate(todo):
        try:
            df = api_get('TaiwanStockPrice', sid)
            if df.empty:
                status[sid] = 'no_data'
            else:
                df.to_parquet(ST_DIR / f'price_{sid}.parquet')
                status[sid] = 'done'
        except Exception as e:
            print(f'{sid} 失敗(下輪重試): {e}')
            continue
        status_p.write_text(json.dumps(status))
        if (k + 1) % 25 == 0:
            rate = (k + 1) / max(time.time() - t0, 1) * 3600
            print(f'進度 {k+1}/{len(todo)}(~{rate:.0f} 檔/hr)')
    print('本輪結束:', pd.Series(status).value_counts().to_dict())


if __name__ == '__main__':
    main()
