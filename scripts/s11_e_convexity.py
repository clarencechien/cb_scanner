#!/usr/bin/env python3
"""
S11-E:CB 本體凸性檢驗(月頻)

假說:低轉換溢價 + 近面額的 CB = 便宜凸性(債底擋下檔、轉換權吃上檔)。
若市場對凸性定價無效率,該子集月報酬分布應呈:左尾截斷 + 右尾開放 +
成本後均值 >= 0。這是 S11 唯一不做多正股的假說(正股三案已全滅)。

資料:cb_universe_monthly(逐月首交易日全市場 CB 行情,2007–2026)。
  買:月 M 抽樣日收盤(僅限當日**有成交**者,拒用停滯參價)
  賣:月 M+1 抽樣日收盤(有成交)或參價(無成交,標記 stale)
  溢價率:CB價 /(100×正股價/轉換價)−1,轉換價用月 M−1 CBTRN 表(PIT)
  下櫃截斷:M+1 不在宇宙 → 無法定價出場,剔除並計數(方向雙向:
  轉換成功強贖 vs 到期還款,誠實列示規模)
成本:買賣手續費 0.1425%×2(免證交稅)+ 滑價敏感度 0.5%/1%/2% 來回。
輸出:results/s11_e_raw_tables.md + s11_e_obs.parquet
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CB_DIR = ROOT / 'data' / 'cb'
ST_DIR = ROOT / 'data' / 'stock'
RES = ROOT / 'results'

FEE = 0.001425 * 2
PREM_BUCKETS = [(-np.inf, 0.05, '<5%'), (0.05, 0.15, '5-15%'),
                (0.15, 0.40, '15-40%'), (0.40, np.inf, '>40%')]
PRICE_BUCKETS = [(-np.inf, 100, '<100'), (100, 110, '100-110'),
                 (110, 130, '110-130'), (130, np.inf, '>130')]
ERAS = [('2013-17', '2013', '2017'), ('2018-21', '2018', '2021'),
        ('2022-26', '2022', '2026')]


def load_close(sid):
    p = ST_DIR / f'price_{sid}.parquet'
    if not p.exists():
        return None
    df = pd.read_parquet(p)[['date', 'close']].copy()
    df['date'] = pd.to_datetime(df['date'])
    s = pd.to_numeric(df.set_index('date')['close'], errors='coerce')
    s[s <= 0] = np.nan
    return s.sort_index()


def summarize(x, min_n=30):
    x = pd.Series(x).dropna().astype(float)
    if len(x) < min_n:
        return None
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else np.nan
    return {'n': len(x), 'mean': x.mean(), 'median': x.median(),
            'win': (x > 0).mean(), 'p10': x.quantile(.1),
            'p90': x.quantile(.9), 't': t}


def main():
    panel = pd.read_parquet(CB_DIR / 'cb_universe_monthly.parquet')
    panel['date'] = pd.to_datetime(panel['date'])
    panel['ym'] = panel['date'].dt.strftime('%Y%m')
    panel = panel.sort_values(['code', 'date'])

    conv = pd.read_parquet(CB_DIR / 'cb_conv_price_monthly.parquet')
    conv = conv.drop_duplicates(['bond', 'ym'], keep='last')
    conv = conv[conv['conv_price'] > 0]
    conv_map = conv.set_index(['bond', 'ym'])['conv_price']

    months = sorted(panel['ym'].unique())
    nxt = dict(zip(months[:-1], months[1:]))
    by_month = {ym: g.set_index('code') for ym, g in panel.groupby('ym')}

    stock_cache = {}

    def stock_close_at(sid, d):
        if sid not in stock_cache:
            stock_cache[sid] = load_close(sid)
        s = stock_cache[sid]
        if s is None:
            return np.nan
        pos = s.index.searchsorted(d, side='right') - 1
        if pos < 0 or (d - s.index[pos]).days > 10:
            return np.nan
        return s.iloc[pos]

    obs, truncated = [], 0
    for ym, g in by_month.items():
        if ym not in nxt or ym < '201301':
            continue
        ym1 = nxt[ym]
        g1 = by_month[ym1]
        prev_ym = str(pd.Period(ym[:4] + '-' + ym[4:], freq='M') - 1).replace('-', '')
        for code, r in g.iterrows():
            if not (pd.notna(r['close']) and (r['amount'] or 0) > 0):
                continue                        # 當日無成交 → 不可執行
            cp = conv_map.get((code, prev_ym), np.nan)
            s = stock_close_at(code[:4], r['date'])
            prem = (r['close'] / (100 * s / cp) - 1
                    if np.isfinite(s) and pd.notna(cp) and cp > 0 else np.nan)
            if code not in g1.index:
                truncated += 1                  # 次月已下櫃,無出場價
                continue
            r1 = g1.loc[code]
            exit_px, stale = r1['close'], False
            if not pd.notna(exit_px):
                exit_px, stale = r1['ref_price_next'], True
            if not pd.notna(exit_px) or exit_px <= 0:
                continue
            obs.append({'code': code, 'ym': ym, 'date': r['date'],
                        'price': r['close'], 'premium': prem,
                        'ret': exit_px / r['close'] - 1, 'stale_exit': stale})
    df = pd.DataFrame(obs)
    df.to_parquet(RES / 's11_e_obs.parquet')
    print(f'觀察 {len(df)} 債·月;下櫃截斷 {truncated};'
          f'stale 出場 {df.stale_exit.mean()*100:.0f}%')

    lines = ['# S11-E CB 本體凸性(自動輸出)\n',
             f'月頻;買=月初有成交收盤,賣=次月初收盤(stale 出場佔 '
             f'{df.stale_exit.mean()*100:.0f}%);下櫃截斷 {truncated} 件'
             f'(無出場價,剔除)。報酬為毛報酬,費用 {FEE*100:.2f}% '
             '另計於判讀。\n']

    def block(seg, label):
        lines.append(f'\n### {label}(n={len(seg)})\n')
        lines.append('| 溢價桶 | n | mean | med | 勝率 | P10/P90 | t |')
        lines.append('|---|---|---|---|---|---|---|')
        for lo, hi, lab in PREM_BUCKETS:
            s = summarize(seg.loc[(seg.premium > lo) & (seg.premium <= hi), 'ret'])
            if s:
                lines.append(f'| {lab} | {s["n"]} | {s["mean"]*100:+.2f}% '
                             f'| {s["median"]*100:+.2f}% | {s["win"]*100:.0f}% '
                             f'| {s["p10"]*100:+.1f}%/{s["p90"]*100:+.1f}% '
                             f'| {s["t"]:+.1f} |')
            else:
                lines.append(f'| {lab} | <30 | - | - | - | - | - |')

    lines.append('\n## 全樣本 × 溢價桶\n')
    for era, lo, hi in ERAS + [('全期', '2013', '2026')]:
        block(df[(df.ym >= lo) & (df.ym <= hi + '13')], era)

    lines.append('\n## 核心子集:溢價 <15% 且價格 95–115(便宜凸性帶)\n')
    core = df[(df.premium < 0.15) & (df.price >= 95) & (df.price <= 115)]
    for era, lo, hi in ERAS + [('全期', '2013', '2026')]:
        block2 = core[(core.ym >= lo) & (core.ym <= hi + '13')]
        s = summarize(block2['ret'])
        if s:
            lines.append(f'- {era}:n={s["n"]},mean {s["mean"]*100:+.2f}%,'
                         f'med {s["median"]*100:+.2f}%,勝率 {s["win"]*100:.0f}%,'
                         f'P10/P90 {s["p10"]*100:+.1f}%/{s["p90"]*100:+.1f}%,'
                         f't {s["t"]:+.1f}')
        else:
            lines.append(f'- {era}:n<30')

    lines.append('\n## 價格桶 × 左尾(債底測試,全期)\n')
    lines.append('| 價格桶 | n | mean | med | 勝率 | P10/P90 | P1 |')
    lines.append('|---|---|---|---|---|---|---|')
    for lo, hi, lab in PRICE_BUCKETS:
        seg = df.loc[(df.price > lo) & (df.price <= hi), 'ret'].dropna()
        if len(seg) >= 30:
            lines.append(f'| {lab} | {len(seg)} | {seg.mean()*100:+.2f}% '
                         f'| {seg.median()*100:+.2f}% | {(seg>0).mean()*100:.0f}% '
                         f'| {seg.quantile(.1)*100:+.1f}%/{seg.quantile(.9)*100:+.1f}% '
                         f'| {seg.quantile(.01)*100:+.1f}% |')
    (RES / 's11_e_raw_tables.md').write_text('\n'.join(lines))
    print('→ results/s11_e_raw_tables.md')


if __name__ == '__main__':
    main()
