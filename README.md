# cb_scanner — S11 可轉債假說驗證(台股結構性 edge 研究)

## TL;DR:所以 CB 到底可不可以搞?

**原本的假設(買發 CB 公司的股票)——不可以搞,而且要反著用。**

原始假說是:公司發了可轉債,就有強烈動機把股價做到轉換價之上
(轉換成功=債務變股本、不用還錢),所以正股應該會漲。
實測 2013–2026、含所有已下櫃債的完整樣本,**這個故事是反的**:

1. **公司發 CB 後,股票平均跌給你看**——發行後一年,正股中位數
   輸櫃買指數 14.5 個百分點,只有 31% 的機率贏大盤,13 年來
   三個市場環境都一樣。原因:發債時點是公司挑的(股價高估時發),
   之後是均值回歸+稀釋+套利盤賣壓。
2. **股價跌到轉換價附近不會有人「護盤」**——所謂磁吸支撐不存在。
3. **賣回日之前公司也不會拉股價**——公司缺錢時的選擇是「下修
   轉換價」(改遊戲規則,一紙公告),不是花真錢買股票。
4. **下修轉換價本身又是一個賣出訊號**——下修後 120 天股票中位數
   再輸大盤 12.2 個百分點。

一句話:**看到「發 CB」或「下修轉換價」,不要買,持有的要警戒。**
這兩條反向規則是本次研究最有價值的產出(零成本、14 年穩定)。

**意外的活口(買 CB 本身,不是買股票)——統計上可以,執行上很勉強,
先觀察不下單。** 低轉換溢價(<15%)、價格貼近面額(95–115)的 CB,
因為「債底擋跌、轉股權吃漲」的不對稱,月均毛報酬 +1.25%、14 年
每年都是正的。但:CB 市場很薄(一半的債整天沒成交),買賣價差
就能吃掉大半利潤(滑價 1% 來回→淨年化約 7%;2% 就歸零),
整個策略容量只有幾千萬台幣,純散戶尺度。按本專案鐵律:
**先跑 6 個月影子模式(只記錄不下單)驗證真的買得到,才談上線。**

## 五案判決(給要看數字的人,2026-07-07 收官)

| 假說 | 判決 | 關鍵數字 |
|---|---|---|
| H-A 發行後正股動能 | **否證+反轉** | 發行後 250d 正股中位輸櫃買指數 14.5pp、勝率 31%;2013–17 / 2018–21 / 2022–26 三年代同向(−14.5 / −14.3 / −15.0);vs 等權 CB 發行人同儕仍 −18.2pp |
| H-B 轉換價磁吸 | **否證** | 35,764 債·月:磁吸帶(股價/轉換價 0.90–1.00)後續報酬與鄰桶無異,型態是動能不是支撐 |
| H-C 賣回日行事曆 | **否證** | 賣回前 120d「做價期」超額中位 −6.7%、勝率 35%(n=452);價外子集也無效果。公司的洩壓閥是下修轉換價,不是做股價 |
| S11-D 下修事件(正股) | **否證** | 下修 ≥10% 後 120d 超額中位 −12.2%、勝率 28%,三年代同向;「下修過頭到價內」也救不回 |
| S11-E CB 本體凸性 | **未否證→影子** | 溢價<15% 且價 95–115:月均毛 +1.25%、14 年逐年全正、P10/P90 −3.4%/+6.2%(右偏 1.8×);滑價 1% 來回淨年化 ~7%、2% 即死;容量 ~3–6 千萬台幣 |

**可用產出(via negativa 第五、六條)**:公司發 CB 後一年內正股不做多、
既有持股視為出場警訊;公司下修轉換價 ≥10% 同樣是賣出警訊。

**附帶發現**:CB 發行人是慢性弱勢池 —— 存續期任一時點、任一價位,
60d 超額中位 −3~−4%(vs 櫃買指數)。做多任何「CB 發行人正股」策略,
起跑線在水面下。

**兩個新地雷**:(1) 基準指數 regime —— 2025-06→2026-07 TAIEX +112%,
中小型股嚴重落後,單一大盤基準會把超額全壓負(已改三基準並列);
(2) CB 存活者偏誤加倍 —— 2013–24 首見的債 83% 已下櫃,用「存續名單」
做的 CB 回測直接作廢(本研究用逐月歷史行情檔重建 PIT 宇宙)。

**沒殺死的**:S11-E 執行面(T+1 可執行性需逐日 CB 行情)、下修事件的
CB 端反應、打新(外部資料)。正股方向已全數驗畢,不再回頭。

## 報告索引

- [`results/s11_summary.md`](results/s11_summary.md) — 總判決
- [`results/s11_0_inventory.md`](results/s11_0_inventory.md) — 資料盤點(資料源決策、宇宙、流動性、溢價分布)
- [`results/s11_a_event_study.md`](results/s11_a_event_study.md) — H-A 判讀(+ [原始表格](results/s11_a_raw_tables.md))
- [`results/s11_b_magnet.md`](results/s11_b_magnet.md) — H-B 判讀(+ [原始表格](results/s11_b_raw_tables.md))
- [`results/s11_c_put_calendar.md`](results/s11_c_put_calendar.md) — H-C 判讀(+ [原始表格](results/s11_c_raw_tables.md))
- [`results/s11_d_reset_events.md`](results/s11_d_reset_events.md) — 下修事件判讀(+ [原始表格](results/s11_d_raw_tables.md))
- [`results/s11_e_convexity.md`](results/s11_e_convexity.md) — CB 凸性判讀(+ [原始表格](results/s11_e_raw_tables.md))

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
python scripts/s11_d_reset_events.py            # 下修事件
python scripts/s11_e_convexity.py               # CB 凸性
```

資料來源:櫃買中心公開 API(CB 條款、賣回權、逐日行情 CSV)、
MOPS 轉換變動月表、FinMind 匿名層(正股與指數日價)。
FinMind 的 CB 專屬資料集需付費會員,本研究未使用。

專案憲法見 [`CLAUDE.md`](CLAUDE.md),歷史脈絡見 [`HANDOFF_S11.md`](HANDOFF_S11.md)。
