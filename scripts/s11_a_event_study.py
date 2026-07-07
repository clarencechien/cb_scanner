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
超額:三個基準並列(鐵律 #7:對照同時段)——
  xM = vs TAIEX(加權指數;大型股偏誤,2025-26 瘋牛時會高估負超額)
  xO = vs TPEx 櫃買指數(CB 發行人多為中小/上櫃,較貼)
  xE = vs 等權發行人指數(全體 CB 發行人日均報酬累積;近似值,
       視窗為 entry 日收盤起算,差一個進場日盤中,20d+ 視窗可忽略)
輸出:results/s11_a_raw_tables.md
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


def build_ew_index():
    """等權 CB 發行人指數:全體已抓正股 close-to-close 日均報酬累積。"""
    rets = []
    for p in ST_DIR.glob('price_*.parquet'):
        sid = p.stem.replace('price_', '')
        if sid in ('TAIEX', 'TPEX_INDEX'):
            continue
        df = pd.read_parquet(p)[['date', 'close']]
        df['date'] = pd.to_datetime(df['date'])
        s = pd.to_numeric(df.set_index('date')['close'], errors='coerce')
        s[s <= 0] = np.nan
        r = s.sort_index().pct_change()
        r = r.replace([np.inf, -np.inf], np.nan)
        # 鐵律 #3:單日 |r|>40% 視為分割/減資殘影,不入指數
        r[r.abs() > 0.4] = np.nan
        rets.append(r.rename(sid))
    mat = pd.concat(rets, axis=1)
    ew = mat.mean(axis=1, skipna=True)
    level = (1 + ew.fillna(0)).cumprod()
    return level


def ew_window_return(level, entry_date, h):
    idx = level.index
    pos = idx.searchsorted(pd.Timestamp(entry_date))
    if pos >= len(idx) or pos + h >= len(idx):
        return np.nan
    return level.iloc[pos + h] / level.iloc[pos] - 1


def summarize(df, col):
    x = df[col].dropna().astype(float)
    if len(x) < 5:
        return None
    t = x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if x.std() > 0 else np.nan
    return {'n': len(x), 'mean': x.mean(), 'median': x.median(),
            'win': (x > 0).mean(), 'p10': x.quantile(.1),
            'p90': x.quantile(.9), 't': t}


def main():
    bench_m = load_price('TAIEX')
    bench_o = load_price('TPEX_INDEX')
    if bench_m is None or bench_o is None:
        sys.exit('缺 TAIEX / TPEX_INDEX,先跑 s11_a_fetch_stocks.py')
    print('建等權發行人指數...')
    ew = build_ew_index()
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
        fm = fwd_returns(bench_m, e.date, HORIZONS)
        fo = fwd_returns(bench_o, e.date, HORIZONS)
        if fr is None or fm is None or fo is None:
            continue
        pos = px.index.searchsorted(fr['entry_date'])
        split = detect_split(px, pos, min(pos + 250, len(px) - 1),
                             bench_m['close'])
        row = {'bond': e.bond, 'stock_id': e.stock_id, 'date': e.date,
               'variant': e.variant, 'suspect_split': split}
        for h in HORIZONS:
            rh = fr[h]
            row[f'r{h}'] = rh
            for tag, bh in [('M', fm[h]), ('O', fo[h]),
                            ('E', ew_window_return(ew, fr['entry_date'], h))]:
                ok = pd.notna(rh) and pd.notna(bh)
                row[f'x{tag}{h}'] = (rh - bh) if ok else np.nan
        rows.append(row)
    res = pd.DataFrame(rows)
    res.to_parquet(RES / 's11_a_events.parquet')
    print(f'有價格可算的事件:{len(res)};缺價格股票 {len(miss)} 檔')

    lines = ['# S11-A 發行日事件研究(自動輸出)\n',
             '超額基準:xM=加權指數、xO=櫃買指數、xE=等權CB發行人指數\n']
    for var in ['V1', 'V2']:
        sub = res[(res.variant == var) & (~res.suspect_split)]
        lines.append(f'\n## {var}(排除疑似分割 '
                     f'{int(res[res.variant==var].suspect_split.sum())} 件)\n')
        for era, lo, hi in ERAS + [('全期', '2013-01-01', '2026-12-31')]:
            seg = sub[(sub.date >= lo) & (sub.date <= hi)]
            lines.append(f'\n### {era}(n={len(seg)})\n')
            lines.append('| h | n | 原始mean | 原始med | xM med | xO mean '
                         '| xO med | xO 勝率 | xO P10/P90 | xO t | xE med |')
            lines.append('|---|---|---|---|---|---|---|---|---|---|---|')
            for h in HORIZONS:
                sO = summarize(seg, f'xO{h}')
                if not sO:
                    lines.append(f'| {h}d | <5 | - | - | - | - | - | - | - | - | - |')
                    continue
                sR = summarize(seg, f'r{h}')
                sM = summarize(seg, f'xM{h}')
                sE = summarize(seg, f'xE{h}')
                lines.append(
                    f'| {h}d | {sO["n"]} '
                    f'| {sR["mean"]*100:+.1f}% | {sR["median"]*100:+.1f}% '
                    f'| {sM["median"]*100:+.1f}% '
                    f'| {sO["mean"]*100:+.1f}% | {sO["median"]*100:+.1f}% '
                    f'| {sO["win"]*100:.0f}% '
                    f'| {sO["p10"]*100:+.1f}%/{sO["p90"]*100:+.1f}% '
                    f'| {sO["t"]:+.1f} '
                    f'| {(sE["median"]*100 if sE else float("nan")):+.1f}% |')
    (RES / 's11_a_raw_tables.md').write_text('\n'.join(lines))
    print('→ results/s11_a_raw_tables.md / s11_a_events.parquet')


if __name__ == '__main__':
    main()
