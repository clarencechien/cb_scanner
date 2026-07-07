#!/usr/bin/env python3
"""
S11-0: FinMind 可轉債資料 —— 探測 + 可續跑抓取
用法:
  python scripts/s11_0_fetch_cb.py probe    # 先跑:探測資料集名稱與欄位
  python scripts/s11_0_fetch_cb.py fetch    # 再跑:抓基本資料 + 逐檔日行情
token 讀環境變數 FINMIND_TOKEN(專案根目錄 .env)。
鐵律:REQ_INTERVAL 6.1s、不平行、可續跑。詳見 CLAUDE.md。
"""
import os, sys, json, time
from pathlib import Path

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TOKEN = os.environ.get('FINMIND_TOKEN', '')
if not TOKEN:
    sys.exit('缺 FINMIND_TOKEN:在專案根目錄建立 .env,內容 FINMIND_TOKEN=xxx')

API = 'https://api.finmindtrade.com/api/v4/data'
ROOT = Path(__file__).resolve().parents[1]
CB_DIR = ROOT / 'data' / 'cb'
CB_DIR.mkdir(parents=True, exist_ok=True)
REQ_INTERVAL = 6.1
_last = [0.0]

# FinMind CB 相關資料集候選名(以 probe 實測為準,勿信記憶)
CANDIDATES = [
    'TaiwanStockConvertibleBondInfo',
    'TaiwanStockConvertibleBondDaily',
    'TaiwanStockConvertibleBondDailyOverview',
    'TaiwanStockConvertibleBondInstitutionalInvestors',
]


def api_get(dataset, data_id=None, start_date=None, retries=3):
    wait = REQ_INTERVAL - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    params = {'dataset': dataset, 'token': TOKEN}
    if data_id:
        params['data_id'] = data_id
    if start_date:
        params['start_date'] = start_date
    for attempt in range(retries):
        try:
            r = requests.get(API, params=params, timeout=60)
            _last[0] = time.time()
            if r.status_code in (402, 429):
                print(f'  限流({r.status_code}),睡 10 分鐘')
                time.sleep(600)
                continue
            r.raise_for_status()
            j = r.json()
            if 'data' not in j:
                raise RuntimeError(str(j)[:200])
            return pd.DataFrame(j['data'])
        except requests.exceptions.RequestException as e:
            print(f'  第 {attempt+1} 次失敗: {e},睡 30s')
            time.sleep(30)
    raise RuntimeError(f'{dataset}/{data_id} 重試失敗')


def probe():
    """探測每個候選資料集:能不能拿、欄位長怎樣。"""
    report = {}
    for ds in CANDIDATES:
        try:
            df = api_get(ds)
            report[ds] = {'rows': len(df), 'cols': list(df.columns)}
            print(f'[OK] {ds}: {len(df)} 列')
            print(f'     欄位: {list(df.columns)}')
            if len(df):
                print(df.head(3).to_string())
        except Exception as e:
            report[ds] = {'error': str(e)[:200]}
            print(f'[FAIL] {ds}: {e}')
    (CB_DIR / 'probe_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2))
    print(f'\n報告已存 {CB_DIR / "probe_report.json"}')
    print('下一步:確認 Info 資料集裡的債券代號欄名與轉換價/發行日欄名,'
          '必要時修改 fetch() 的欄位對應,再跑 fetch。')


def fetch():
    """抓 CB 基本資料(1 request)+ 逐檔日行情(可續跑)。"""
    info_p = CB_DIR / 'cb_info.parquet'
    if info_p.exists():
        info = pd.read_parquet(info_p)
    else:
        info = api_get('TaiwanStockConvertibleBondInfo')
        if info.empty:
            sys.exit('Info 資料集為空,先跑 probe 確認資料集名稱')
        info.to_parquet(info_p)
    print(f'CB 檔數: {len(info)}; 欄位: {list(info.columns)}')

    # 債券代號欄名依 probe 結果調整(常見:cb_id)
    id_col = 'cb_id' if 'cb_id' in info.columns else info.columns[0]
    ids = info[id_col].astype(str).drop_duplicates().tolist()

    status_p = CB_DIR / 'status.json'
    status = json.loads(status_p.read_text()) if status_p.exists() else {}
    todo = [i for i in ids if i not in status]
    print(f'待抓 {len(todo)} / 共 {len(ids)}(續跑自動跳過已完成)')

    for k, cid in enumerate(todo):
        try:
            df = api_get('TaiwanStockConvertibleBondDaily', cid, '2015-01-01')
            if df.empty:
                status[cid] = 'no_data'
            else:
                df.to_parquet(CB_DIR / f'daily_{cid}.parquet')
                status[cid] = 'done'
        except Exception as e:
            print(f'{cid} 失敗(下輪重試): {e}')
            continue
        status_p.write_text(json.dumps(status))
        if (k + 1) % 25 == 0:
            print(f'進度 {k+1}/{len(todo)}')
    print('本輪結束:', pd.Series(status).value_counts().to_dict())


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    {'probe': probe, 'fetch': fetch}[mode]()
