#!/usr/bin/env python3
"""
S11-A:CB 發行(上櫃)後正股動能事件研究

H-A:CB 發行後 6–18 個月,正股相對大盤有系統性正超額(發行人有制度動機
在賣回/到期前把股價做上轉換價)。

事件定義(兩個變體,互為穩健性檢查):
  V1 exact  上櫃日(ISSBD5 ListingDate ∪ convSearch 掛牌日期)。
            精確但受存活者偏誤污染(ISSBD5 只有存續債;convSearch 只有
            近兩年)——偏誤方向:提前轉換出場的成功案例會消失 → 對 H-A
            是「向下」偏誤(2023 前樣本)。
  V2 PIT    逐月宇宙首見日(cb_universe_monthly,含已下櫃債,無存活者
            偏誤;粒度:上櫃後 0–1 個月內首個月初交易日)。

進場:事件日後首個交易日(T+1)開盤價(鐵律 #5)。
報酬:T+1 開盤 → T+1+h 收盤,h ∈ {20, 60, 120, 250} 交易日。
超額:同視窗 TAIEX 同法計算,相減(鐵律 #7:對照同時段)。
輸出:results/s11_a_event_study.md
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

HORIZONS = [20, 60, 120, 250]
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
    df = pd.read_parquet(p)
    df = df[['date', 'open', 'close']].copy()
    df['date'] = pd.to_datetime(df['date'])
    # 鐵律 #2:零價格 → NaN
    for c in ['open', 'close']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
        df.loc[df[c] <= 0, c] = np.nan
    return df.set_index('date').sort_index()


def fwd_returns(px, event_date, horizons):
    """T+1 開盤進場 → T+1+h 收盤。回傳 {h: r} 或 None(資料不足)。"""
    idx = px.index
    pos = idx.searchsorted(pd.Timestamp(event_date), side='right')
    if pos >= len(idx):
        return None
    entry = px['open'].iloc[pos]
    if not np.isfinite(entry):
        # 開盤缺值(停牌等)→ 往後找 3 天內首個有效開盤
        for q in range(pos + 1, min(pos + 4, len(idx))):
            entry = px['open'].iloc[q]
            if np.isfinite(entry):
                pos = q
                break
        else:
            return None
    out = {'entry_date': idx[pos]}
    for h in horizons:
        if pos + h < len(idx):
            exitp = px['close'].iloc[pos + h]
            r = exitp / entry - 1 if np.isfinite(exitp) else np.nan
        else:
            r = np.nan
        out[h] = r
    return out


def detect_split(px, pos_lo, pos_hi, bench_close):
    """鐵律 #3:視窗內單日 < -25% 且大盤 > -10% → 疑似分割/異常,剔除。"""
    seg = px['close'].iloc[pos_lo:pos_hi + 1]
    r = seg.pct_change()
    if not len(r):
        return False
    b = bench_close.reindex(seg.index).pct_change()
    sus = (r < -0.25) & (b.fillna(0) > -0.10)
    return bool(sus.any())


def build_events():
    """回傳 DataFrame[bond_code, stock_id, event_date, variant]"""
    events = []

    # V1 exact:ISSBD5(存續)∪ convSearch(近兩年,含已下櫃)
    info = pd.read_parquet(CB_DIR / 'cb_info_issbd5.parquet')
    info = info[info['BondCode'].str.strip().ne('')].copy()
    for _, r in info.iterrows():
        ld = str(r['ListingDate']).strip()
        if len(ld) == 8 and ld.isdigit():
            events.append((r['BondCode'].strip(), r['IssuerCode'].strip(),
                           f'{ld[:4]}-{ld[4:6]}-{ld[6:]}', 'V1'))
    lst = pd.read_parquet(CB_DIR / 'cb_recent_listed.parquet')
    for _, r in lst.iterrows():
        ad = roc_to_ad(r['掛牌日期'])
        sid = str(r['發行機構代碼']).strip()
        if ad and re.fullmatch(r'\d{4}', sid):
            m = re.search(r'bond_id=(\w+)', str(r['發行資料']))
            bond = m.group(1) if m else sid + '?'
            events.append((bond, sid, ad, 'V1'))

    # V2 PIT:逐月宇宙首見
    summ = pd.read_parquet(CB_DIR / 'cb_universe_summary.parquet')
    for _, r in summ.iterrows():
        code = str(r['code']).strip()
        if re.fullmatch(r'\d{5,6}', code):
            events.append((code, code[:4], r['first_seen'], 'V2'))

    ev = pd.DataFrame(events, columns=['bond', 'stock_id', 'date', 'variant'])
    ev['date'] = pd.to_datetime(ev['date'])
    ev = ev.drop_duplicates(['bond', 'variant'])
    # V2 首見=宇宙起點(2007-01)者非新發行,剔除左截斷
    umin = ev.loc[ev.variant == 'V2', 'date'].min()
    ev = ev[~((ev.variant == 'V2') & (ev.date == umin))]
    return ev


def summarize(df, col):
    x = df[col].dropna().astype(float)
    if len(x) < 5:
        return None
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else np.nan
    return {'n': len(x), 'mean': x.mean(), 'median': x.median(),
            'win': (x > 0).mean(), 'p10': x.quantile(.1),
            'p90': x.quantile(.9), 't': t}


def main():
    bench = load_price('TAIEX')
    if bench is None:
        sys.exit('缺 TAIEX,先跑 s11_a_fetch_stocks.py')
    ev = build_events()
    print(f'事件數:{ev.groupby("variant").size().to_dict()}')

    rows = []
    miss = set()
    for _, e in ev.iterrows():
        px = load_price(e.stock_id)
        if px is None:
            miss.add(e.stock_id)
            continue
        fr = fwd_returns(px, e.date, HORIZONS)
        fb = fwd_returns(bench, e.date, HORIZONS)
        if fr is None or fb is None:
            continue
        pos = px.index.searchsorted(fr['entry_date'])
        split = detect_split(px, pos, min(pos + 250, len(px) - 1),
                             bench['close'])
        row = {'bond': e.bond, 'stock_id': e.stock_id, 'date': e.date,
               'variant': e.variant, 'suspect_split': split}
        for h in HORIZONS:
            rh, bh = fr[h], fb[h]
            row[f'r{h}'] = rh
            ok = pd.notna(rh) and pd.notna(bh)
            row[f'x{h}'] = (rh - bh) if ok else np.nan
        rows.append(row)
    res = pd.DataFrame(rows)
    res.to_parquet(RES / 's11_a_events.parquet')
    print(f'有價格可算的事件:{len(res)};缺價格股票 {len(miss)} 檔')

    lines = ['# S11-A 發行日事件研究(自動輸出)\n']
    for var in ['V1', 'V2']:
        sub = res[(res.variant == var) & (~res.suspect_split)]
        lines.append(f'\n## {var}(排除疑似分割 '
                     f'{int(res[res.variant==var].suspect_split.sum())} 件)\n')
        for era, lo, hi in ERAS + [('全期', '2013-01-01', '2026-12-31')]:
            seg = sub[(sub.date >= lo) & (sub.date <= hi)]
            lines.append(f'\n### {era}(n={len(seg)})\n')
            lines.append('| h | n | 超額mean | 超額median | 勝率 | P10 | P90 | t |')
            lines.append('|---|---|---|---|---|---|---|---|')
            for h in HORIZONS:
                s = summarize(seg, f'x{h}')
                if s:
                    lines.append(
                        f'| {h}d | {s["n"]} | {s["mean"]*100:+.1f}% '
                        f'| {s["median"]*100:+.1f}% | {s["win"]*100:.0f}% '
                        f'| {s["p10"]*100:+.1f}% | {s["p90"]*100:+.1f}% '
                        f'| {s["t"]:+.1f} |')
                else:
                    lines.append(f'| {h}d | <5 | - | - | - | - | - | - |')
    (RES / 's11_a_raw_tables.md').write_text('\n'.join(lines))
    print('→ results/s11_a_raw_tables.md / s11_a_events.parquet')


if __name__ == '__main__':
    main()
