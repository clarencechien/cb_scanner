#!/usr/bin/env python3
"""
S11-C:賣回日行事曆事件研究

H-C:賣回權基準日前 N 個月,發行人有制度動機把股價做上轉換價
(否則持有人行使賣回權,公司要掏現金)→ 正股在賣回日前應有異常正超額,
且效果應集中在「價外」(股價 < 現時轉換價)子集——那才是動機所在。

設計:
  事件 = (債券, 賣回日期)  來源 cb_put_provision(2011–2028,含已下櫃債)
  視窗 = 賣回日前 120 交易日 → 賣回日(約 6 個月「做價期」)
         對照:賣回日 → 賣回日後 60 交易日(動機消失期)
  超額 = vs 櫃買指數(xO)為主,vs 加權(xM)並列
  分組 = 視窗起點的 moneyness:股價 / 現時轉換價(CBTRN 月表)
         OTM(<0.9)/ NEAR(0.9–1.1)/ ITM(>1.1)
輸出:results/s11_c_raw_tables.md + s11_c_events.parquet
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
RES.mkdir(exist_ok=True)

PRE_H = 120     # 賣回日前視窗(交易日)
POST_H = 60     # 賣回日後對照視窗
ERAS = [('2013-17', '2013-01-01', '2017-12-31'),
        ('2018-21', '2018-01-01', '2021-12-31'),
        ('2022-26', '2022-01-01', '2026-12-31')]


def roc_to_ad(s):
    m = re.match(r'(\d{2,3})/(\d{2})/(\d{2})', str(s).strip())
    if not m:
        return None
    return f'{int(m.group(1)) + 1911:04d}-{m.group(2)}-{m.group(3)}'


def load_price(sid):
    p = ST_DIR / f'price_{sid}.parquet'
    if not p.exists():
        return None
    df = pd.read_parquet(p)[['date', 'open', 'close']].copy()
    df['date'] = pd.to_datetime(df['date'])
    for c in ['open', 'close']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
        df.loc[df[c] <= 0, c] = np.nan
    return df.set_index('date').sort_index()


def window_return(px, end_date, pre_h=None, post_h=None):
    """pre: close[end-pre_h] → close[end];post: close[end] → close[end+post_h]"""
    idx = px.index
    pos = idx.searchsorted(pd.Timestamp(end_date), side='right') - 1
    if pos < 0:
        return np.nan
    if pre_h is not None:
        lo = pos - pre_h
        if lo < 0:
            return np.nan
        a, b = px['close'].iloc[lo], px['close'].iloc[pos]
    else:
        hi = pos + post_h
        if hi >= len(idx):
            return np.nan
        a, b = px['close'].iloc[pos], px['close'].iloc[hi]
    if not (np.isfinite(a) and np.isfinite(b)):
        return np.nan
    return b / a - 1


def summarize(x):
    x = pd.Series(x).dropna().astype(float)
    if len(x) < 5:
        return None
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else np.nan
    return {'n': len(x), 'mean': x.mean(), 'median': x.median(),
            'win': (x > 0).mean(), 'p10': x.quantile(.1),
            'p90': x.quantile(.9), 't': t}


def main():
    put = pd.read_parquet(CB_DIR / 'cb_put_provision.parquet')
    put['put_date'] = pd.to_datetime(put['賣回日期'].map(roc_to_ad))
    put['bond'] = put['代號'].astype(str).str.strip()
    put = put.dropna(subset=['put_date'])
    put = put[put['bond'].str.fullmatch(r'\d{5,6}')]
    put['stock_id'] = put['bond'].str[:4]

    conv = pd.read_parquet(CB_DIR / 'cb_conv_price_monthly.parquet')
    conv = conv.drop_duplicates(['bond', 'ym'], keep='last')
    conv_map = conv.set_index(['bond', 'ym'])['conv_price']

    bm = load_price('TAIEX')
    bo = load_price('TPEX_INDEX')
    if bm is None or bo is None:
        sys.exit('缺基準指數')

    rows = []
    for _, e in put.iterrows():
        px = load_price(e.stock_id)
        if px is None:
            continue
        # moneyness 於視窗起點(賣回日前 ~6 個月)
        m0 = (e.put_date - pd.DateOffset(months=7)).strftime('%Y%m')
        cp = conv_map.get((e.bond, m0), np.nan)
        idx = px.index
        pos0 = idx.searchsorted(e.put_date - pd.DateOffset(months=6))
        s0 = px['close'].iloc[pos0] if pos0 < len(idx) else np.nan
        mny = s0 / cp if np.isfinite(s0) and pd.notna(cp) and cp > 0 else np.nan

        row = {'bond': e.bond, 'stock_id': e.stock_id,
               'put_date': e.put_date, 'moneyness': mny}
        for tag, b in [('', px), ('_m', bm), ('_o', bo)]:
            row[f'pre{tag}'] = window_return(b, e.put_date, pre_h=PRE_H)
            row[f'post{tag}'] = window_return(b, e.put_date, post_h=POST_H)
        rows.append(row)
    res = pd.DataFrame(rows)
    for w in ['pre', 'post']:
        res[f'{w}_xM'] = res[w] - res[f'{w}_m']
        res[f'{w}_xO'] = res[w] - res[f'{w}_o']
    res.to_parquet(RES / 's11_c_events.parquet')
    print(f'事件 {len(res)} 件(賣回日 {res.put_date.min().date()} ~ '
          f'{res.put_date.max().date()})')

    def block(seg, label, lines):
        lines.append(f'\n### {label}(n={len(seg)})\n')
        lines.append('| 視窗 | n | 原始med | xO mean | xO med | xO 勝率 '
                     '| xO P10/P90 | xO t |')
        lines.append('|---|---|---|---|---|---|---|---|')
        for w, nm in [('pre', '前120d'), ('post', '後60d')]:
            s = summarize(seg[f'{w}_xO'])
            if not s:
                lines.append(f'| {nm} | <5 | - | - | - | - | - | - |')
                continue
            sr = summarize(seg[w])
            lines.append(
                f'| {nm} | {s["n"]} | {sr["median"]*100:+.1f}% '
                f'| {s["mean"]*100:+.1f}% | {s["median"]*100:+.1f}% '
                f'| {s["win"]*100:.0f}% '
                f'| {s["p10"]*100:+.1f}%/{s["p90"]*100:+.1f}% '
                f'| {s["t"]:+.1f} |')

    lines = ['# S11-C 賣回日行事曆(自動輸出)\n',
             '事件=賣回基準日;pre=日前120交易日累積,post=日後60交易日;'
             'xO=超額vs櫃買指數\n']
    hist = res[res.put_date <= pd.Timestamp.today()]
    for era, lo, hi in ERAS + [('全期(僅歷史)', '2011-01-01', '2026-07-07')]:
        block(hist[(hist.put_date >= lo) & (hist.put_date <= hi)], era, lines)
    lines.append('\n## Moneyness 分組(全期,視窗起點 股價/轉換價)\n')
    for lab, lo, hi in [('OTM <0.9', -np.inf, 0.9),
                        ('NEAR 0.9–1.1', 0.9, 1.1),
                        ('ITM >1.1', 1.1, np.inf)]:
        seg = hist[(hist.moneyness > lo) & (hist.moneyness <= hi)]
        block(seg, lab, lines)
    block(hist[hist.moneyness.isna()], '無轉換價資料', lines)
    (RES / 's11_c_raw_tables.md').write_text('\n'.join(lines))
    print('→ results/s11_c_raw_tables.md / s11_c_events.parquet')


if __name__ == '__main__':
    main()
