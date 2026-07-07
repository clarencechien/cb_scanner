#!/usr/bin/env python3
"""
S11-D:下修轉換價事件研究(正股)

H-D:公司下修轉換價 = 對「把債轉掉」的制度承諾(降低轉換門檻,
用稀釋換免還錢)。若制度動機有價,下修後正股應有異常報酬
(方向存疑:利好=轉換更容易;利空=公司自認股價回不去)。

資料與污染處理:
  轉換價變動來自 MOPS CBTRN 月表(月對月)。**除權息也會調轉換價**,
  且集中 7–9 月(探勘:降幅>=5% 事件 85% 落在 7–9 月)。分離規則:
    主定義   降幅 >= 10%(真下修通常一刀 10–30%;除息調整多 <8%)
    敏感度   5–10% 降幅、且非 7–9 月(淡季 = 較純的下修)
  事件日 = 月表「重設日期」(生效日,公司已公告)→ T+1 可執行。
視窗:pre(-60d→0,含公告反應)/ post(T+1 開盤→+20/60/120 收盤)
超額:vs 櫃買指數(xO)。分年代、分事件時 moneyness(新轉換價)。
輸出:results/s11_d_raw_tables.md + s11_d_events.parquet
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

POST_H = [20, 60, 120]
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


def summarize(x, min_n=8):
    x = pd.Series(x).dropna().astype(float)
    if len(x) < min_n:
        return None
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else np.nan
    return {'n': len(x), 'mean': x.mean(), 'median': x.median(),
            'win': (x > 0).mean(), 'p10': x.quantile(.1),
            'p90': x.quantile(.9), 't': t}


def build_reset_events():
    conv = pd.read_parquet(CB_DIR / 'cb_conv_price_monthly.parquet')
    conv = conv.drop_duplicates(['bond', 'ym'], keep='last')
    conv = conv[conv['conv_price'] > 0].sort_values(['bond', 'ym'])
    conv['prev'] = conv.groupby('bond')['conv_price'].shift(1)
    conv['prev_ym'] = conv.groupby('bond')['ym'].shift(1)
    conv['chg'] = conv['conv_price'] / conv['prev'] - 1
    # 只比相鄰月(2019 H2 缺檔會造成跨月假事件)
    per = pd.PeriodIndex(conv['ym'].str[:4] + '-' + conv['ym'].str[4:], freq='M')
    per_p = pd.PeriodIndex(conv['prev_ym'].fillna('190001').str[:4] + '-' +
                           conv['prev_ym'].fillna('190001').str[4:], freq='M')
    conv = conv[(per - per_p).map(lambda x: x.n) == 1]
    ev = conv[conv['chg'] <= -0.05].copy()
    ev['reset_ad'] = ev['reset_date'].map(roc_to_ad)
    ev = ev.dropna(subset=['reset_ad'])
    ev['reset_ad'] = pd.to_datetime(ev['reset_ad'])
    # 重設日期應落在 prev_ym~ym 區間附近,偏離 45 天以上者(舊日期殘留)剔除
    mid = pd.PeriodIndex(ev['ym'].str[:4] + '-' + ev['ym'].str[4:],
                         freq='M').to_timestamp()
    ev = ev[(ev['reset_ad'] - mid).dt.days.abs() <= 45]
    ev['stock_id'] = ev['bond'].str[:4]
    ev['month'] = ev['ym'].str[4:]
    ev['is_big'] = ev['chg'] <= -0.10
    ev['off_season'] = ~ev['month'].isin(['07', '08', '09'])
    return ev


def main():
    bo = load_price('TPEX_INDEX')
    if bo is None:
        sys.exit('缺櫃買指數')
    ev = build_reset_events()
    print(f'候選事件:{len(ev)}(>=10% 下修 {ev.is_big.sum()};'
          f'5-10% 淡季 {((~ev.is_big) & ev.off_season).sum()})')

    rows = []
    for _, e in ev.iterrows():
        px = load_price(e.stock_id)
        if px is None:
            continue
        idx = px.index
        pos = idx.searchsorted(e.reset_ad, side='right')
        if pos >= len(idx) or pos < 60:
            continue
        entry = px['open'].iloc[pos]
        if not np.isfinite(entry):
            continue
        s0 = px['close'].iloc[pos]
        row = {'bond': e.bond, 'stock_id': e.stock_id, 'date': e.reset_ad,
               'chg': e.chg, 'is_big': e.is_big, 'off_season': e.off_season,
               'mny_new': s0 / e.conv_price if np.isfinite(s0) else np.nan}
        # pre:-60d 收盤 → 事件日收盤
        pre_lo = px['close'].iloc[pos - 60]
        pre_hi = px['close'].iloc[pos - 1]
        bpos = bo.index.searchsorted(e.reset_ad, side='right')
        if np.isfinite(pre_lo) and np.isfinite(pre_hi) and bpos >= 60:
            bpre = (bo['close'].iloc[bpos - 1] / bo['close'].iloc[bpos - 60] - 1)
            row['pre_xO'] = pre_hi / pre_lo - 1 - bpre
        for h in POST_H:
            if pos + h < len(idx) and bpos + h < len(bo):
                r = px['close'].iloc[pos + h] / entry - 1
                b = (bo['close'].iloc[bpos + h] / bo['open'].iloc[bpos] - 1)
                # 鐵律 #3:疑似分割剔除
                if pd.notna(r) and r < -0.5 and b > -0.15:
                    r = np.nan
                row[f'x{h}'] = r - b if pd.notna(r) else np.nan
        rows.append(row)
    res = pd.DataFrame(rows)
    res.to_parquet(RES / 's11_d_events.parquet')
    print(f'有價格可算:{len(res)}')

    def block(seg, label, lines):
        lines.append(f'\n### {label}(n={len(seg)})\n')
        lines.append('| 視窗 | n | mean | med | 勝率 | P10/P90 | t |')
        lines.append('|---|---|---|---|---|---|---|')
        for col, nm in [('pre_xO', '前60d'), ('x20', '後20d'),
                        ('x60', '後60d'), ('x120', '後120d')]:
            s = summarize(seg[col] if col in seg else [])
            if not s:
                lines.append(f'| {nm} | <8 | - | - | - | - | - |')
                continue
            lines.append(f'| {nm} | {s["n"]} | {s["mean"]*100:+.1f}% '
                         f'| {s["median"]*100:+.1f}% | {s["win"]*100:.0f}% '
                         f'| {s["p10"]*100:+.1f}%/{s["p90"]*100:+.1f}% '
                         f'| {s["t"]:+.1f} |')

    lines = ['# S11-D 下修轉換價事件(自動輸出)\n',
             '事件=重設生效日;超額 vs 櫃買指數;pre=前60d(含公告反應),'
             'post=T+1 開盤起算。\n']
    big = res[res.is_big]
    lines.append('\n## 主定義:降幅 >= 10%(下修為主)\n')
    for era, lo, hi in ERAS + [('全期', '2013-01-01', '2026-12-31')]:
        block(big[(big.date >= lo) & (big.date <= hi)], era, lines)
    lines.append('\n## 敏感度:5–10% 且非 7–9 月(淡季下修)\n')
    block(res[(~res.is_big) & res.off_season], '全期', lines)
    lines.append('\n## 敏感度:>=10% 且非 7–9 月(最純)\n')
    block(big[big.off_season], '全期', lines)
    lines.append('\n## 下修後 moneyness 分組(主定義,全期)\n')
    for lab, lo_b, hi_b in [('下修後仍價外 <0.95', -np.inf, 0.95),
                            ('下修到價平 0.95-1.05', 0.95, 1.05),
                            ('下修過頭 >1.05', 1.05, np.inf)]:
        block(big[(big.mny_new > lo_b) & (big.mny_new <= hi_b)], lab, lines)
    (RES / 's11_d_raw_tables.md').write_text('\n'.join(lines))
    print('→ results/s11_d_raw_tables.md')


if __name__ == '__main__':
    main()
