# OMS × Villa Finder 別墅查詢頁 整合開發指示

> 給 Alan／Claude Code。目標：讓 TC 在 OMS 的 Request 上一鍵開啟峇里島別墅查詢頁，選定別墅後把結果貼回 OMS，由 OMS 記錄成本、訂金、餘款與付款提醒。
> 查詢頁端需要配合的功能**已經完成並上線**（§2），本文件只剩 OMS 端要做的事。
> 原始碼與技術文件：https://github.com/andrewnowing/outo-bali-villas （`docs/TECH.md`、`src/`）

## 0. 先讀這些（Claude Code 開始前）

1. 讀本文件全部。
2. 讀 OMS 現有的「住宿元件」資料模型與 Request 頁面程式，找出：住宿元件的資料表／model、Request 編號欄位名稱、現有「成本」「售價」「幣別」欄位、現有的到期提醒機制（若有）。
3. 把你找到的對應關係填進 §6 的對照表，再開始改程式。不要先猜欄位名稱。

## 1. 流程（做完後 TC 的操作）

| 步 | 誰 | 在哪 | 做什麼 |
|---|---|---|---|
| 1 | TC | OMS Request 的住宿元件 | 按「查峇里島別墅」→ 新分頁開查詢頁，日期、房數、人數、Outo 訂單編號自動帶入 |
| 2 | TC | 查詢頁 | 篩選、看地圖、展開別墅 → 按「確認預訂並寄信」寄訂房信給 Villa Finder（信裡已含 Outo 訂單編號） |
| 3 | TC | 查詢頁 | 按「複製 OMS 回填資料」→ 剪貼簿得到一段 JSON |
| 4 | TC | OMS 住宿元件 | 按「貼上 Villa Finder 資料」→ 貼上 JSON → 欄位自動填好 → 存檔 |
| 5 | OMS | 自動 | 算淨付、訂金、餘款、期限；到期前 7 天提醒 |
| 6 | TC | OMS | 收到 Villa Finder 確認信後回填「Villa Finder 訂單編號」與「確認信上的佣金率」（若與預設不同） |

## 2. 查詢頁已提供的接口（不用再做）

### 2.1 開啟連結（OMS → 查詢頁）

```
https://outo-bali-villas.vercel.app/?ci=YYYY-MM-DD&co=YYYY-MM-DD&br=N&gu=N&ref=<Outo訂單編號>&q=<別墅名稱關鍵字，選填>
```

| 參數 | 必填 | 說明 |
|---|---|---|
| `ci`, `co` | 是（兩個一起） | 入住日、退房日，ISO 日期 |
| `br` | 否 | 至少幾房，1–6 |
| `gu` | 否 | 入住人數，1–21；0 或不給＝不限 |
| `ref` | 否 | Outo 訂單編號，最多 40 字；會自動填進訂房信的「Outo 訂單編號」欄位，並出現在回填 JSON 的 `outo_ref` |
| `q` | 否 | 別墅名稱關鍵字，最多 80 字（之後 TC 從 OMS 回看某間別墅時用） |

### 2.2 回填資料（查詢頁 → OMS，經剪貼簿）

TC 在別墅展開區按「複製 OMS 回填資料」，剪貼簿內容是一個 JSON 物件：

```json
{
  "source": "villa-finder",
  "villa_slug": "villa-mucha-canggu",
  "villa_name": "Villa Mucha",
  "area": "Canggu",
  "rate_type": "public",
  "checkin": "2026-11-10",
  "checkout": "2026-11-12",
  "nights": 2,
  "bedrooms": 3,
  "guests": 6,
  "currency": "USD",
  "published_total": 270,
  "promo_total": null,
  "promo_label": null,
  "nightly_from": null,
  "commission_pct": 10,
  "net_to_vf": 243,
  "deposit_pct": 50,
  "deposit_amount": 135,
  "balance_due": "2026-09-11",
  "cancellation_policy": "VF-STD-2026-10-05",
  "availability": "available",
  "availability_checked_at": "2026-10-05T15:38:15.588Z",
  "outo_ref": "OUTO-2026-1234",
  "villa_finder_url": "https://www.villa-finder.com/en/canggu/villa-mucha-canggu",
  "page_url": "https://outo-bali-villas.vercel.app/?ci=2026-11-10&co=2026-11-12&br=3&q=Villa%20Mucha"
}
```

| 欄位 | 型別 | 說明 |
|---|---|---|
| `source` | 固定 `"villa-finder"` | 用來判斷貼上的是不是本系統的資料 |
| `villa_slug` | string | Villa Finder 的別墅代號，**全系統主鍵**，同一間別墅永遠相同 |
| `villa_name`, `area` | string | 顯示用 |
| `rate_type` | `"portal"` 或 `"public"` | portal＝同業後台 118 間（佣金以 Villa Finder 確認信為準，常見 20%）；public＝官網直售 1,019 間（佣金 10%） |
| `checkin`, `checkout`, `nights` | date, date, int | |
| `bedrooms` | int 或 null | 報價所用的房數格局 |
| `guests` | int 或 null | 查詢時的人數 |
| `currency` | 固定 `"USD"` | |
| `published_total` | number 或 null | 公告價總額（整段住宿）。浮動價別墅為 null |
| `promo_total`, `promo_label` | number／string 或 null | 套用促銷後的總額與促銷名稱；沒有促銷為 null |
| `nightly_from` | number 或 null | 浮動價別墅的每晚起價；固定價為 null |
| `commission_pct` | number 或 null | public 固定 10；portal 為 null（等確認信） |
| `net_to_vf` | number 或 null | 付給 Villa Finder 的淨額＝(promo_total 或 published_total) × (1 − 佣金率)；portal 因佣金未知為 null |
| `deposit_pct`, `deposit_amount` | 50, number 或 null | 訂金 50%，以 promo_total 或 published_total 計 |
| `balance_due` | date | 餘款期限＝入住前 60 天。**可能早於今天**（臨時訂單），此時餘款視為立即到期 |
| `cancellation_policy` | 固定 `"VF-STD-2026-10-05"` | Villa Finder 2026-10-05 書面確認的標準條款，內容見 §4 |
| `availability` | `available` / `booked` / `unknown` | 複製當下的房況 |
| `availability_checked_at` | ISO datetime | 房況資料的更新時間 |
| `outo_ref` | string 或 null | 從開啟連結的 `ref` 帶回 |
| `villa_finder_url` | url | 別墅在 Villa Finder 的頁面 |
| `page_url` | url | 回到查詢頁同一筆的連結 |

## 3. OMS 端要做的（第一階段）

### 3.1 住宿元件新增欄位

| 欄位 | 型別 | 必填 | 來源 |
|---|---|---|---|
| `vf_slug` | string(80) | 是 | JSON `villa_slug` |
| `vf_name` | string(120) | 是 | `villa_name` |
| `vf_area` | string(60) | 否 | `area` |
| `vf_rate_type` | enum portal/public | 是 | `rate_type` |
| `vf_checkin`, `vf_checkout` | date | 是 | `checkin`, `checkout` |
| `vf_nights` | int | 是 | `nights` |
| `vf_bedrooms` | int | 否 | `bedrooms` |
| `vf_guests` | int | 否 | `guests` |
| `vf_published_total_usd` | decimal(10,2) | 否 | `published_total` |
| `vf_promo_total_usd` | decimal(10,2) | 否 | `promo_total` |
| `vf_promo_label` | string(120) | 否 | `promo_label` |
| `vf_nightly_from_usd` | decimal(10,2) | 否 | `nightly_from` |
| `vf_commission_pct` | decimal(5,2) | 是 | `commission_pct`；null 時預設：portal→20、public→10，並標記「待確認信確認」 |
| `vf_net_usd` | decimal(10,2) | 系統算 | (promo_total ?? published_total) × (1 − commission_pct/100)，四捨五入到分 |
| `vf_deposit_usd` | decimal(10,2) | 系統算 | 基準總額 × 50% |
| `vf_deposit_due` | date | 系統算 | 存檔當天（Villa Finder：確認後即付） |
| `vf_balance_usd` | decimal(10,2) | 系統算 | 基準總額 − 訂金 |
| `vf_balance_due` | date | 系統算 | checkin − 60 天；若早於今天則＝今天 |
| `vf_payment_mode` | enum per_booking/monthly | 是，預設 per_booking | monthly 只有 portal 且 Villa Finder 同意時由 TC 改 |
| `vf_deposit_paid_at`, `vf_balance_paid_at` | date | 否 | TC 付款後填 |
| `vf_booking_ref` | string(60) | 否 | Villa Finder 確認信上的訂單編號，TC 回填 |
| `vf_cancellation_policy` | string(40) | 是 | `cancellation_policy` |
| `vf_availability_at_copy` | string(20) | 否 | `availability` |
| `vf_url`, `vf_page_url` | url | 否 | `villa_finder_url`, `page_url` |
| `vf_payload_raw` | json/text | 是 | 原始 JSON 整段存起來，之後對帳用 |

匯率：**成本以 USD 記錄**，不在此欄位組換算台幣；若 OMS 的成本報表需要台幣，用 OMS 既有的匯率規則（財務要先決定用訂單日或付款日匯率，見 §5）。

### 3.2 Request 頁／住宿元件 UI

1. 按鈕「查峇里島別墅」：只在目的地為峇里島（或 Indonesia）的 Request 顯示；點了 `window.open()` §2.1 的網址，參數取自 Request 的入住日、退房日、房數（沒有就不帶）、人數、Request 編號。
2. 按鈕「貼上 Villa Finder 資料」：開一個對話框，一個多行文字框，TC 貼上 JSON 後按「帶入」：
   - 解析失敗或 `source !== "villa-finder"` → 顯示「這不是 Villa Finder 查詢頁複製的資料，請回查詢頁按『複製 OMS 回填資料』」。
   - 若 `checkin/checkout` 與 Request 日期不同 → 顯示警示但允許帶入（TC 可能刻意改日期）。
   - 若 `availability === "booked"` → 顯示紅字警示「複製當時顯示已被訂，請先向 Villa Finder 確認」。
   - 若 `commission_pct` 為 null → 帶入預設值並在欄位旁標「待確認信確認」。
   - 帶入後所有系統算欄位即時更新。
3. 元件摘要列（顯示文字，照這個格式）：
   `Villa Finder｜{vf_name}（{vf_area}）｜{checkin}–{checkout}｜{bedrooms} 房｜公告價 USD {published_total}{有促銷時：｜促銷價 USD {promo_total}}｜佣金 {commission_pct}%｜淨付 USD {net}｜訂金 USD {deposit}{已付時：✓}｜餘款 USD {balance} 期限 {balance_due}`
4. 條款文字（元件內可展開，供 TC 對客人說明）：
   `取消：入住前 90 天以上沒收 20%；60–89 天沒收 50%；59 天內全額沒收；另收 USD 200 行政費。`
5. 連結：「在 Villa Finder 開啟」（`vf_url`）、「回查詢頁」（`vf_page_url`）。

### 3.3 提醒

| 時機 | 給誰 | 內容 |
|---|---|---|
| `vf_deposit_due` 當天且 `vf_deposit_paid_at` 空 | 該 Request 的 TC | 「Villa Finder 訂金 USD {deposit} 今天到期（Request #{ref}）」 |
| `vf_balance_due` 前 7 天與當天，且 `vf_balance_paid_at` 空 | TC ＋ 財務 | 「Villa Finder 餘款 USD {balance} 將於 {date} 到期（Request #{ref}）」 |
| `vf_payment_mode = monthly`：每月 1 日、15 日前 3 天 | 財務 | 列出該期應付的所有 Villa Finder 訂單與金額 |

用 OMS 既有的提醒／通知機制；沒有的話先用每日一次的排程寄 Email。

### 3.4 退款（取消時）

取消流程若已存在，新增兩個扣項欄位並顯示在退款計算：
- `vf_forfeit_usd`：依取消日距入住日天數自動建議：>90 天→基準總額 × 20%；60–89 天→50%；≤59 天→已付金額 100%。TC 可改。
- `vf_admin_fee_usd`：固定 200。
退給客人的金額由 OMS 既有規則算，這兩項只是成本側的扣除，供財務對帳。

## 4. 商業規則（Villa Finder 2026-10-05 書面確認）

| 項目 | 規則 |
|---|---|
| 正式訂房管道 | Email（查詢頁產生）；WhatsApp 群組只做追問 |
| 同業後台 118 間 | 在後台下 hold 即鎖房；確認信列出租金、佣金、淨額；獨家代理者佣金 20%，可每月 1 日／15 日付款 |
| 官網直售 1,019 間 | 用同業帳號登入 villa-finder.com 直接訂，佣金 10% |
| 付款 | 確認後 50% 訂金；餘款入住前 60 天；臨時訂單入住前付清 |
| 取消 | >90 天沒收 20%；60–89 天 50%；0–59 天已付金額 100%；每筆另收 USD 200 行政費（不退，可抽佣） |
| 加床／三人房 | 逐筆向 Villa Finder 確認，部分別墅不接受 |
| 價格 | 公告價 USD，後台價已含促銷、無隱藏費用 |

## 5. 需要人決定、不要自己猜的事

| 事項 | 誰決定 | 沒決定前怎麼做 |
|---|---|---|
| 成本換算台幣用哪一天匯率 | 財務 | 只存 USD |
| 佣金是扣在淨額還是先付全額再退 | 第一張實際帳單驗證 | 先照「付淨額」做，`vf_payload_raw` 留著 |
| 月結適用範圍 | Andrew 與 Villa Finder | 預設 per_booking |
| 售價怎麼定 | 現行報價規則 | 不做自動售價 |

## 6. 對照表（Claude Code 讀完 OMS 程式後填）

| 本文件名稱 | OMS 實際位置（檔案／資料表／欄位） |
|---|---|
| Request | |
| Request 編號 | |
| 住宿元件 | |
| 目的地欄位 | |
| 入住／退房日 | |
| 人數、房數 | |
| 成本欄位（USD） | |
| 提醒機制 | |
| 取消／退款流程 | |

## 7. 完成條件（驗收）

1. 峇里島 Request 上有「查峇里島別墅」，開出的網址帶正確的 `ci/co/br/gu/ref`；非峇里島 Request 不顯示。
2. 貼上 §2.2 範例 JSON 後，欄位全部正確帶入，`vf_net_usd = 243`、`vf_deposit_usd = 135`、`vf_balance_usd = 135`、`vf_balance_due` 因早於今天而等於今天。
3. 貼上非本系統的文字時被擋下並顯示指定訊息。
4. `availability: "booked"` 的 JSON 帶入時顯示紅字警示。
5. `rate_type: "portal"` 且 `commission_pct: null` 時預設 20 並標「待確認信確認」。
6. 摘要列文字格式與 §3.2 第 3 點一致。
7. 餘款期限前 7 天的提醒會寄出（用一筆 `vf_balance_due` 設為 7 天後的測試資料驗證）。
8. 既有非 Villa Finder 的住宿元件完全不受影響。

## 8. 本次不做

- 查詢頁嵌入 OMS（iframe）或房況同步進 OMS。
- Villa Finder 確認信自動解析。
- 對客售價自動計算。
- 官網直售的線上付款串接。
- 自動向查詢頁或 Villa Finder 發 API（查詢頁沒有寫入 API；資料只經剪貼簿）。
