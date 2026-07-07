#!/usr/bin/env python3
"""
S11-B:轉換價磁吸檢驗

H-B:股價位於轉換價下緣(-10%~0%)時有異常支撐 → 後續報酬應優於
其他 moneyness 區間的同類觀察。

設計(月頻橫斷面):
  觀察 = (債, 月):CBTRN 月表(月 M)的現時轉換價,配 月 M+1 首個
  交易日的正股收盤 → moneyness = 股價/轉換價。月表於 M+1 月初已公布,
  PIT 安全。同一發行人多檔債時取轉換價最低者(磁吸最近的下緣)。
  fwd = 訊號日後 20/60 交易日正股報酬,超額 vs 櫃買指數(xO)。
  分桶: <0.7 / 0.7-0.9 / 0.9-1.0(磁吸帶)/ 1.0-1.1 / 1.1-1.3 / >1.3
  對照 = 同期其他桶(對照組同時段,鐵律 #7)。
注意:同債逐月觀察重疊 → 粗略 t 高估,以中位數/勝率為主要判準。
輸出:results/s11_b_raw_tables.md + s11_b_obs.parquet
"""
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CB_DIR = ROOT / 'data' / 'cb'
ST_DIR = ROOT / 'data' / 'stock'
RES = ROOT / 'results'

HORIZONS = [20, 60]
BUCKETS = [(-np.inf, 0.7, '<0.70'), (0.7, 0.9, '0.70-0.90'),
           (0.9, 1.0, '0.90-1.00 磁吸帶'), (1.0, 1.1, '1.00-1.10'),
           (1.1, 1.3, '1.10-1.30'), (1.3, np.inf, '>1.30')]
ERAS = [('2013-17', '2013-01', '2017-12'),
        ('2018-21', '2018-01', '2021-12'),
        ('2022-26', '2022-01', '2026-12')]


def load_close(sid):
    p = ST_DIR / f'price_{sid}.parquet'
    if not p.exists():
        return None
    df = pd.read_parquet(p)[['date', 'close']].copy()
    df['date'] = pd.to_datetime(df['date'])
    s = pd.to_numeric(df.set_index('date')['close'], errors='coerce')
    s[s <= 0] = np.nan
    return s.sort_index()


def summarize(x):
    x = pd.Series(x).dropna().astype(float)
    if len(x) < 30:
        return None
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else np.nan
    return {'n': len(x), 'mean': x.mean(), 'median': x.median(),
            'win': (x > 0).mean(), 't': t}


def main():
    conv = pd.read_parquet(CB_DIR / 'cb_conv_price_monthly.parquet')
    conv = conv.drop_duplicates(['bond', 'ym'], keep='last')
    conv = conv[conv['conv_price'] > 0]
    conv['stock_id'] = conv['bond'].str[:4]
    # 同發行人同月多檔債 → 取轉換價最低者
    conv = (conv.sort_values('conv_price')
                .drop_duplicates(['stock_id', 'ym'], keep='first'))

    bo = load_close('TPEX_INDEX')
    if bo is None:
        sys.exit('缺櫃買指數')
    bo_idx = bo.index

    obs = []
    for sid, gr in conv.groupby('stock_id'):
        px = load_close(sid)
        if px is None:
            continue
        idx = px.index
        for _, r in gr.iterrows():
            # 訊號日 = ym 次月首個交易日
            sig_month = (pd.Period(r['ym'], freq='M') + 1).to_timestamp()
            pos = idx.searchsorted(sig_month)
            if pos >= len(idx):
                continue
            sig_date = idx[pos]
            if sig_date - sig_month > pd.Timedelta(days=15):
                continue                     # 該月已無交易(下市等)
            s0 = px.iloc[pos]
            if not np.isfinite(s0):
                continue
            bpos = bo_idx.searchsorted(sig_date)
            row = {'bond': r['bond'], 'stock_id': sid, 'ym': r['ym'],
                   'date': sig_date, 'mny': s0 / r['conv_price']}
            for h in HORIZONS:
                rr = (px.iloc[pos + h] / s0 - 1
                      if pos + h < len(idx) else np.nan)
                rb = (bo.iloc[bpos + h] / bo.iloc[bpos] - 1
                      if bpos + h < len(bo_idx) else np.nan)
                # 鐵律 #3:視窗內疑似分割 → 剔除
                if pd.notna(rr) and rr < -0.5 and pd.notna(rb) and rb > -0.15:
                    rr = np.nan
                row[f'r{h}'] = rr
                row[f'x{h}'] = rr - rb if pd.notna(rr) and pd.notna(rb) else np.nan
            obs.append(row)
    df = pd.DataFrame(obs)
    df.to_parquet(RES / 's11_b_obs.parquet')
    print(f'觀察 {len(df)} 債·月,{df.stock_id.nunique()} 檔正股,'
          f'{df.ym.min()}~{df.ym.max()}')

    lines = ['# S11-B 轉換價磁吸(自動輸出)\n',
             '觀察=債·月;mny=月初股價/上月轉換價;xO=超額vs櫃買指數;\n'
             '同債逐月重疊 → t 高估,以中位數/勝率為主。\n']
    for era, lo, hi in ERAS + [('全期', '2013-01', '2026-12')]:
        seg = df[(df.ym >= lo.replace('-', '')) & (df.ym <= hi.replace('-', ''))]
        lines.append(f'\n## {era}(n={len(seg)})\n')
        for h in HORIZONS:
            lines.append(f'\n### fwd {h}d\n')
            lines.append('| mny 桶 | n | xO mean | xO med | 勝率 | t |')
            lines.append('|---|---|---|---|---|---|')
            for lo_b, hi_b, lab in BUCKETS:
                s = summarize(seg.loc[(seg.mny > lo_b) & (seg.mny <= hi_b),
                                      f'x{h}'])
                if s:
                    lines.append(f'| {lab} | {s["n"]} | {s["mean"]*100:+.1f}% '
                                 f'| {s["median"]*100:+.1f}% '
                                 f'| {s["win"]*100:.0f}% | {s["t"]:+.1f} |')
                else:
                    lines.append(f'| {lab} | <30 | - | - | - | - |')
    (RES / 's11_b_raw_tables.md').write_text('\n'.join(lines))
    print('→ results/s11_b_raw_tables.md')


if __name__ == '__main__':
    main()
