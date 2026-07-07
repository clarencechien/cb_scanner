# cb_scanner — S11 可轉債假說驗證(台股結構性 edge 研究)

## 懶人包(2026-07-07 收官)

**一句話:三條 CB 假說全數否證,其中 H-A 反轉 —— CB 發行是正股的
賣出警訊,不是買進理由。**

| 假說 | 判決 | 關鍵數字 |
|---|---|---|
| H-A 發行後正股動能 | **否證+反轉** | 發行後 250d 正股中位輸櫃買指數 14.5pp、勝率 31%;2013–17 / 2018–21 / 2022–26 三年代同向(−14.5 / −14.3 / −15.0);vs 等權 CB 發行人同儕仍 −18.2pp |
| H-B 轉換價磁吸 | **否證** | 35,764 債·月:磁吸帶(股價/轉換價 0.90–1.00)後續報酬與鄰桶無異,型態是動能不是支撐 |
| H-C 賣回日行事曆 | **否證** | 賣回前 120d「做價期」超額中位 −6.7%、勝率 35%(n=452);價外子集也無效果。公司的洩壓閥是下修轉換價,不是做股價 |

**可用產出(via negativa 第五條)**:公司發 CB 後一年內,正股不做多;
既有持股把 CB 發行視為出場警訊之一。

**附帶發現**:CB 發行人是慢性弱勢池 —— 存續期任一時點、任一價位,
60d 超額中位 −3~−4%(vs 櫃買指數)。做多任何「CB 發行人正股」策略,
起跑線在水面下。

**兩個新地雷**:(1) 基準指數 regime —— 2025-06→2026-07 TAIEX +112%,
中小型股嚴重落後,單一大盤基準會把超額全壓負(已改三基準並列);
(2) CB 存活者偏誤加倍 —— 2013–24 首見的債 83% 已下櫃,用「存續名單」
做的 CB 回測直接作廢(本研究用逐月歷史行情檔重建 PIT 宇宙)。

**沒殺死的**:CB 本體凸性、下修轉換價公告事件、打新(資料大多已在手,
詳見 summary)。但任何做多正股的變體應死刑推定起步。

## 報告索引

- [`results/s11_summary.md`](results/s11_summary.md) — 總判決
- [`results/s11_0_inventory.md`](results/s11_0_inventory.md) — 資料盤點(資料源決策、宇宙、流動性、溢價分布)
- [`results/s11_a_event_study.md`](results/s11_a_event_study.md) — H-A 判讀(+ [原始表格](results/s11_a_raw_tables.md))
- [`results/s11_b_magnet.md`](results/s11_b_magnet.md) — H-B 判讀(+ [原始表格](results/s11_b_raw_tables.md))
- [`results/s11_c_put_calendar.md`](results/s11_c_put_calendar.md) — H-C 判讀(+ [原始表格](results/s11_c_raw_tables.md))

## 重跑方式(全部零 token、可續跑)

```bash
pip install pandas requests pyarrow lxml python-dotenv
python scripts/s11_0_fetch_cb_tpex.py static    # TPEx 條款/名單(~2 分鐘)
python scripts/s11_0_fetch_cb_tpex.py monthly   # 逐月行情 2007–今(~15 分鐘)
python scripts/s11_0_fetch_cb_tpex.py universe  # 建 PIT 宇宙
python scripts/s11_b_fetch_cbtrn.py             # MOPS 月度轉換價(~4 分鐘)
python scripts/s11_a_fetch_stocks.py            # FinMind 匿名正股(~1.7 小時)
python scripts/s11_a_event_study.py             # H-A
python scripts/s11_b_magnet.py                  # H-B
python scripts/s11_c_put_calendar.py            # H-C
```

資料來源:櫃買中心公開 API(CB 條款、賣回權、逐日行情 CSV)、
MOPS 轉換變動月表、FinMind 匿名層(正股與指數日價)。
FinMind 的 CB 專屬資料集需付費會員,本研究未使用。

專案憲法見 [`CLAUDE.md`](CLAUDE.md),歷史脈絡見 [`HANDOFF_S11.md`](HANDOFF_S11.md)。
