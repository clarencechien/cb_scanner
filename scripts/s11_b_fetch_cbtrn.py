#!/usr/bin/env python3
"""
S11-B 前置:抓 MOPS 轉換公司債轉換變動月表(CBTRN{yyyymm}.htm)

內容:每檔存續 CB 當月的「轉(交)換或認股價格 + 重設日期 + 當月轉換張數」。
月頻現時轉換價 = H-B 磁吸檢驗的核心輸入(ISSBD5 只有發行時轉換價)。
實測至少回溯 2013-01。來源由 TPEx bond/cbnote 的連結發現。

用法:python scripts/s11_b_fetch_cbtrn.py
輸出:data/cb/cbtrn/CBTRN{yyyymm}.htm(原始檔)+ cb_conv_price_monthly.parquet
"""
import io
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data' / 'cb' / 'cbtrn'
OUT.mkdir(parents=True, exist_ok=True)
REQ_INTERVAL = 1.0
HEADERS = {'User-Agent': 'Mozilla/5.0'}


def fetch_all():
    status_p = OUT / 'status.json'
    status = json.loads(status_p.read_text()) if status_p.exists() else {}
    # 非 done(307/404/502)允許重試——307 實測為暫時性保護
    status = {k: v for k, v in status.items() if v == 'done'}
    months = pd.period_range('2013-01', pd.Timestamp.today(), freq='M')
    todo = [str(m).replace('-', '') for m in months]
    todo = [m for m in todo if m not in status]
    print(f'待抓 {len(todo)} 個月')
    for k, ym in enumerate(todo):
        url = f'https://mopsov.twse.com.tw/nas/t120/CBTRN{ym}.htm'
        try:
            r = requests.get(url, timeout=60, headers=HEADERS)
            if r.status_code == 200 and len(r.content) > 2000:
                (OUT / f'CBTRN{ym}.htm').write_bytes(r.content)
                status[ym] = 'done'
            else:
                status[ym] = f'http_{r.status_code}_len{len(r.content)}'
        except requests.exceptions.RequestException as e:
            print(f'{ym} 失敗(下輪重試): {e}')
            time.sleep(10)
            continue
        status_p.write_text(json.dumps(status))
        time.sleep(REQ_INTERVAL)
        if (k + 1) % 24 == 0:
            print(f'進度 {k+1}/{len(todo)}')
    print('本輪結束:', pd.Series(status).value_counts().to_dict())


def parse_all():
    rows = []
    for f in sorted(OUT.glob('CBTRN*.htm')):
        ym = f.stem.replace('CBTRN', '')
        html = f.read_bytes().decode('big5', errors='replace')
        try:
            tables = pd.read_html(io.StringIO(html))
        except ValueError:
            continue
        for t in tables:
            cols = [str(c) for c in t.columns]
            # 欄位版型不只一種(7 欄 / 12 欄...),用欄名對位
            try:
                i_bond = next(i for i, c in enumerate(cols) if '證券' in c)
                i_px = next(i for i, c in enumerate(cols)
                            if '價格' in c and '認股' in c or '轉' in c and '價格' in c)
                i_reset = next((i for i, c in enumerate(cols) if '重設' in c), None)
                i_lots = next((i for i, c in enumerate(cols) if '轉換張數' in c), None)
            except StopIteration:
                continue
            sub = pd.DataFrame({
                'issuer': t.iloc[:, 0], 'bond': t.iloc[:, i_bond],
                'conv_price': t.iloc[:, i_px],
                'reset_date': t.iloc[:, i_reset] if i_reset is not None else None,
                'conv_lots': t.iloc[:, i_lots] if i_lots is not None else None,
            })
            sub['ym'] = ym
            rows.append(sub)
    df = pd.concat(rows, ignore_index=True)
    # issuer/bond 欄是「代號<br>名稱」二合一,拆代號
    for c in ['issuer', 'bond']:
        df[c] = df[c].astype(str).str.extract(r'^(\w+)')[0]
    df['conv_price'] = pd.to_numeric(
        df['conv_price'].astype(str).str.replace(',', ''), errors='coerce')
    df = df[df['bond'].str.fullmatch(r'\d{5,6}', na=False)]
    df.to_parquet(ROOT / 'data' / 'cb' / 'cb_conv_price_monthly.parquet')
    print(f'{df["ym"].nunique()} 個月、{df["bond"].nunique()} 檔債、'
          f'{len(df)} 列 → cb_conv_price_monthly.parquet')


if __name__ == '__main__':
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else 'fetch'
    {'fetch': fetch_all, 'parse': parse_all}[mode]()
