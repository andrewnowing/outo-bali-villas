# Outo 峇里島別墅查詢頁 — 技術說明（給 Alan）

版本：2026-10-05　撰寫：Andrew（由 Claude 整理）
網址：內部版 https://outo-bali-villas.vercel.app ／ 客人版 https://outo-bali-villas.vercel.app/guest
程式與資料：GitHub `andrewnowing/outo-bali-villas`（公開倉庫；原始碼在 `src/`，部署檔在根目錄）

---

## 1. 這個系統做什麼

| 項目 | 內容 |
|---|---|
| 房源 | Villa Finder 的 1,137 間峇里島別墅：118 間「同業後台」（Distribution Portal，有同業價與促銷）＋ 1,019 間「官網直售」（villa-finder.com 公開頁面，佣金 10%） |
| 查詢 | 輸入入住／退房、房數、人數 → 3 秒內列出有空房的別墅、該日期總價與每晚均價（USD／TWD）、促銷、床型、地址、到市區車程、Google 評價、照片、設施、付款與取消條款 |
| 地圖 | Google Maps，依篩選結果顯示圖釘（群聚顯示），可選別墅＋景點算車程 |
| 下訂 | 產生訂房信（寄 bookings@villa-finder.com）或 WhatsApp 訊息（貼到 Outo × Villa Finder 群組）；Villa Finder 表單連結已帶入日期人數 |
| 客人版 /guest | 同一頁面的對外版本：隱藏同業價、佣金、促銷、訂房按鈕與內部連結，只留公告價與基本資訊 |

## 2. 架構

```
使用者瀏覽器 ──► Vercel（靜態網站 index.html / guest.html / pub.js / pub_extra.js / pubav.js / gal/*.json / config.js）
      │                    ▲ git push 自動部署（pubav.js 單獨 commit 不觸發重新部署，見 vercel.json ignoreCommand）
      │
      ├─ 每 2 分鐘 fetch ──► Apps Script「118 間 iCal 房況」(AVAIL_URL)：回傳 {updatedAt, byIcal:{villa:[[from,to],…]}, fx:{rate,at,src}}
      ├─ 每 2 分鐘 fetch ──► raw.githubusercontent.com/…/data/pubav.js：1,019 間官網房源的已訂日期
      ├─ 載入時 ──► Google Maps JavaScript API（圖磚、標記）；匯率 open.er-api.com（USD→TWD，失敗時用 31.9）
      └─ 偵測到異常時 POST ──► Apps Script「Outo villa watchdog」(WATCH_URL)

GitHub Actions（倉庫內 .github/workflows/）
      ├─ refresh-pubav.yml：每 5 分鐘抓 1,019 間公開頁面 → 更新 pubav.js → commit（自我接力，見 §4.2）
      └─ build-gal.yml：每週一重建 gal/<slug>.json（照片分組：臥室／室內／戶外）

Apps Script（Andrew 的 Google 帳號）
      ├─ 118 間 iCal 房況同步：每 5 分鐘讀 Villa Finder 的 iCal 行事曆 → JSON 端點（AVAIL_URL），同時附台銀匯率
      └─ Outo villa watchdog：每 15 分鐘健康檢查 + 接收網頁回報 + 寄信（§6）
```

## 3. 資料來源與檔案

| 檔案（倉庫根目錄） | 內容 | 來源 | 更新方式 |
|---|---|---|---|
| `index.html` / `guest.html` | 整個應用（HTML＋CSS＋JS），兩檔內容相同，`/guest` 路徑切到客人模式 | `src/template_bi.html` + `src/data_bi.js`（118 間資料）+ `src/photos.js` + `src/extra_bi.js`（118 間床型、地址、車程）由 `src/build_deploy.py` 組出 | 手動：改 src → 跑 build → commit |
| `pub.js` | 1,019 間官網房源：名稱、區域、房數格局、季節價表（每房型每晚 USD）、促銷、設施、座標、評分、佣金率、照片清單、說明、政策文字 | `src/vf2/outo_pub.json` 等（從 Villa Finder 公開頁面與搜尋 API 擷取，2026-10-05）經 `src/vf2/convert.py` 產生 | 手動，建議每季重跑一次 |
| `pub_extra.js` | 1,061 間（118＋官網中有座標者）的床型、Google 地址、Google 評分、到各市區車程（開車／步行） | Google Places API（Text Search）、Google Routes API（computeRouteMatrix）一次性查詢；`src/vf2/extra.py` 產生 | 手動，新增別墅時重跑 |
| `pubav.js` | 1,019 間官網房源的已訂日期 `{updatedAt, by:{slug:[[YYMMDD,YYMMDD],…]}, ok, err, history:[最近 120 次]}` | GitHub Actions `scripts/refresh_pubav.py` | 自動，每 5 分鐘 |
| `gal/<slug>.json` | 每間別墅照片分組（bed／out／in／more），含每間臥室床型文字 | GitHub Actions `scripts/build_gal.py` 從公開頁面擷取 | 自動，每週一 |
| `config.js` | `MAPS_KEY`（Google Maps 金鑰，已限制網域）、`WA_GROUP`（WhatsApp 群組連結）、`WATCH_URL`（監控端點） | 手動 | — |
| `api/offer.js` | 原本想做的「即時向 Villa Finder 查價」Vercel function，被 Villa Finder 的 Cloudflare 擋（403），目前停用 | — | — |

照片全部用 Villa Finder 的 CDN 連結（cf-img.villa-finder.com），沒有複製到我們這邊；對外公開使用前需 Villa Finder 同意。

### 3.1 單筆別墅資料欄位（pub.js 的 PUB_VILLAS）

| 欄位 | 意義 |
|---|---|
| `n`, `s`, `a` | 名稱、slug（Villa Finder 網址代號，全系統主鍵）、區域 |
| `src` | `'pub'`＝官網直售；118 間在 data_bi.js 沒有此欄 |
| `b` | 可訂的房數格局，例如 `[2,3,4]` 代表可用 2、3 或 4 房價格訂 |
| `r` | 季節價表：`[起日 YYMMDD, 迄日, 季節碼 L/M/H/P/Q, 最少晚數, 2房價, 3房價, …]`（USD／晚，與 `b` 對應） |
| `dyn`, `dp`, `dpd` | 每日浮動價別墅：無季節表，只存公開站顯示的每晚起價（原價／折扣價） |
| `p` | 促銷文字（原文），由 `parsePromo()` 解析成折扣規則 |
| `x` | 最多人數、員工數、面積、庭院、NIB 營業登記號 |
| `g` | 座標 `lat,lng` |
| `f`, `fe` | 設施（中文對照／英文原文） |
| `vr` | Villa Finder 住客評分 `[分數, 則數]` |
| `com` | 同業佣金率（10／20／null），Villa Finder 10/5 確認官網房源一律 10% |
| `url`, `ba` | 公開頁面網址、價格是否需詢價 |

## 4. 房況更新邏輯

### 4.1 118 間同業後台（Apps Script → AVAIL_URL）
1. Villa Finder 同業後台提供每間別墅的 iCal 行事曆網址（存在 data_bi.js 的 `i` 欄位）。
2. Apps Script 每 5 分鐘讀全部 iCal，把 VEVENT 轉成「已訂區間」，連同台銀即期賣出匯率一起輸出 JSON。
3. 網頁每 2 分鐘讀 AVAIL_URL；`updatedAt` 比目前新才套用（`applyAvail()`），並寫進「房況更新歷史紀錄」。
4. iCal 本身可能比 Villa Finder 後台慢幾分鐘，頁面與操作說明都註明「以 Villa Finder 回覆為準」。

### 4.2 1,019 間官網直售（GitHub Actions → pubav.js）
1. `scripts/refresh_pubav.py` 以 12 個執行緒抓 1,019 個公開頁面（約 56 秒），讀取頁面裡 `#request-form` 的 `:unavailabilities` 屬性（JSON：`[{from,to},…]`）。
2. 語意換算：Villa Finder 的 `from`／`to` 是「不可入住的區間」，實際被鎖住的晚數是 from−1 到 to；存成半開區間 `[from−1, to+1)`，與 iCal 格式一致。
3. 保護規則：
   - 單頁失敗（非 200、逾時）→ 保留該別墅上一版資料，不清空。
   - 成功數低於 70% → 整次放棄，不改檔，workflow 失敗（避免被 Villa Finder 封鎖時寫入壞資料）。
   - 超過 30% 頁面找不到 `:unavailabilities` 屬性 → 判定 Villa Finder 改版，整次放棄並在紀錄標 `noattr`（否則會把所有別墅寫成「有空房」）。
   - 遇到 HTTP 429 退避 15／30／45 秒重試。
4. 每次執行寫入 `history`（時間、成功數、失敗數、變動間數、noattr），保留 120 筆；網頁的「房況更新歷史紀錄」會把這些列出來。
5. 排程：GitHub 的 cron（`*/5`）實測不可靠（連續一小時沒觸發），所以改成「自我接力」：每次 run 結束時等到距開始滿 300 秒，再用 `workflow_dispatch` 觸發下一次。接力步驟設 `if: always()`，抓取失敗也會排下一次；若 3 分鐘內已有另一條接力在跑則不重複。實測間隔 5 分 07 秒。
6. 網頁每 2 分鐘從 `raw.githubusercontent.com/…/data/pubav.js` 讀最新房況（不等 Vercel 重新部署）。機器人只 commit 到 `data` 分支，`vercel.json` 的 `git.deploymentEnabled.data=false` 讓這些 commit 完全不建立 Vercel 部署。（2026-10-05 前機器人 commit 到 main，即使 `ignoreCommand` 跳過建置，每次仍算一次部署，一天約 288 次，超過免費方案每天 100 次上限，導致網站無法更新。）main 上的 pubav.js 只是初次載入用的備份。

### 4.3 「有空房」判定
- `conflicts(v, ci, co)`：已訂區間與查詢區間重疊即「已被訂」。
- 沒有任何房況資料的別墅標黃色「沒有房況資料」。
- 已訂區間長於 180 天且 90 天內開始 → 標「長期封房，可能暫停接單」。

## 5. 價格邏輯

| 類型 | 計算 |
|---|---|
| 118 間同業後台 | 依季節價表逐晚加總（每晚對到所在季節、所選房數格局），檢查最少晚數；促銷由 `promoCalc()` 解析文字規則（例如「入住 9/4–12/4 八折」「住 7 付 6」）套到總價，顯示為「同業折扣價」。價格為 Villa Finder 公告價（Published Rate），佣金以 Villa Finder 確認信為準 |
| 1,019 間官網（固定季節價） | 同上，從公開頁面的 Rates 表取得；顯示「官網直售價」與「同業佣金 10%，約 USD X」 |
| 1,019 間官網（每日浮動價） | 公開頁沒有季節表，只顯示「每晚 USD X 起」，實際總價請到 Villa Finder 頁面查（連結已帶日期人數） |
| 資料清洗 | Villa Finder 有少數別墅把印尼盾當美金標（例如 USD 2,800,000／晚）；每晚價超過 USD 20,000 一律視為錯誤、不顯示（`badrate`／`baddp`） |
| 幣別 | 內部價格以 USD 為準；TWD 用 open.er-api 中間價（或 Apps Script 回傳的台銀即期賣出）換算，頁面標示匯率與時間，失敗時用 31.9 並標示 |
| 每晚預算篩選 | 以每晚均價（固定價）或每晚起價（浮動價）比對 |

已知待確認：Villa Finder 10/5 表示「後台顯示的價格已含促銷」；本頁是以後台季節價表再套促銷，若季節價表本身已是促銷後價格會重複打折。需登入後台抽查一間有促銷的別墅對照。

## 6. 監控與自我檢測

| 元件 | 做什麼 | 失敗時 |
|---|---|---|
| Apps Script「Outo villa watchdog」每 15 分鐘 | A 官網房況超過 20 分鐘沒更新；B 最近一次抓取失敗 >300 間或 noattr >300；C GitHub 接力鏈超過 15 分鐘沒有 run；D 網站 HTTP 非 200；E 118 間房況超過 3 小時沒更新（需填 AVAIL_URL） | 寄信到 andrew@outo.co；C 會用 GitHub token 自動重新啟動接力鏈；同一警報 6 小時內只寄一次，恢復時寄「已恢復」 |
| 網頁端回報（`watchReport()`） | Google Maps 回報金鑰／帳務／網域錯誤（`gm_authFailure`）、Maps 程式載入失敗、瀏覽器讀到的房況超過 30 分鐘沒更新 | POST 到 WATCH_URL → 寄信；同一瀏覽器每種異常 6 小時最多回報一次 |
| 試用到期提醒 | Google Cloud 免費試用預計 2027-01-03 到期（到期不升級，地圖、地址、距離全部停） | 到期前 30／14／7／3／1 天各寄一封 |
| 心跳信 | 每週一 09:00 寄「監控運作中」 | 沒收到代表監控本身停了 |
| Google Cloud 預算 | 每月 USD 50，達 50／90／100% 寄信 | — |
| GitHub | 失敗的 workflow 會寄信給倉庫擁有者（需在 GitHub 通知設定開啟） | — |

監控腳本原始碼：`src/watchdog.gs`；指令碼屬性 `ALERT_TO`（收信人）、`GH_TOKEN`（fine-grained token，只給此倉庫 Actions 讀寫）。

## 7. 預訂流程（網頁端）

1. TC 選日期、房數、人數 → 篩選 → 展開別墅。
2. 「確認預訂並寄信」：在頁面填主要旅客、人數、小孩年齡、Outo 訂單編號、航班、特殊需求 → 預覽信件 → 用 `mailto:` 開 Gmail 寄到 bookings@villa-finder.com（副本可填）；寄出紀錄存在瀏覽器 localStorage 的「訂房紀錄」（只在該台電腦）。
3. 「用 WhatsApp 下訂」：產生同內容訊息，複製並開啟 Outo × Villa Finder 群組，TC 貼上送出（WhatsApp 不允許預填群組訊息）。Villa Finder 表示 Email 是正式管道，群組只做追問。
4. 官網直售別墅：用同業後台相同帳密登入 villa-finder.com 直接訂（佣金 10%），頁面的「Villa Finder 頁面」連結已帶日期人數。

## 8. 外部服務與費用

| 服務 | 用途 | 費用 |
|---|---|---|
| Vercel（Hobby） | 靜態網站 | 免費（100 GB 流量／月） |
| GitHub Actions | 每 5 分鐘抓房況、每週重建相簿 | 公開倉庫免費；若改私人倉庫每月約 8,000 分鐘，超過 2,000 分鐘額度 |
| Google Maps Platform（專案 outo-villa-maps） | 地圖、一次性地址查詢與車程矩陣 | 地圖載入每月約 1–3 千次，遠低於 USD 200 免費額度；一次性查詢已花約 USD 60–80（試用額度） |
| Google Apps Script | iCal 同步、監控 | 免費 |
| open.er-api.com | 匯率 | 免費 |

## 9. 已知限制與風險

| 項目 | 說明 |
|---|---|
| Villa Finder 可能封鎖 | 每 5 分鐘抓 1,019 頁 ≈ 每天 29 萬次請求。被封時資料會停在上一版，監控會寄信；降到 15 分鐘是最直接的解法 |
| Villa Finder 改版 | 欄位名稱改變時抓取會自動中止並寄信，需人工更新 `refresh_pubav.py` 的解析規則 |
| 倉庫膨脹 | 每 5 分鐘一個約 600 KB 的 commit，估每月 +0.5–1 GB；3 個月後需把 pubav.js 搬到獨立分支並定期清歷史 |
| 即時查價不可用 | Villa Finder 的 Cloudflare 擋掉 Vercel 的 IP；GitHub 的 IP 沒被擋，所以抓取放在 GitHub Actions |
| 無登入 | /guest 與內部版都沒有登入機制，網址知道就能看；內部版有同業價與佣金，請勿外流 |
| 訂房紀錄只在本機 | localStorage，不同電腦看不到彼此的紀錄；串接 OMS 後應改存 OMS |
| 原始資料時效 | 1,019 間的季節價、促銷、設施是 2026-10-05 的快照，房況是即時的；價格建議每季重抓 |

## 10. 怎麼改、怎麼部署

| 要改什麼 | 做法 |
|---|---|
| 畫面、文字、邏輯 | 改 `src/template_bi.html` → `python3 src/build_deploy.py` → 把產出的 `index.html` 複製成 `guest.html` → commit、push，Vercel 自動部署 |
| 118 間資料 | 改 `src/data_bi.js` / `src/extra_bi.js` 後同上 |
| 1,019 間資料 | 重抓公開頁面（`src/vf2/` 的擷取流程）→ `convert.py` → `extra.py` → 覆蓋 `pub.js` / `pub_extra.js` |
| 設定 | `config.js`（金鑰、群組連結、監控端點） |
| 抓取頻率 | `.github/workflows/refresh-pubav.yml` 的 `sleep_for` 計算（目前 300 秒） |
| 監控 | Apps Script 專案「Outo villa watchdog」（Andrew 帳號）；常數 `STALE_MIN`、`MUTE_HOURS`、`TRIAL_END` |

## 11. 串接 OMS 的建議接口

| 階段 | 做法 | 需要頁面端配合 |
|---|---|---|
| 1 連結帶參數 | OMS 住宿元件加按鈕，開 `https://outo-bali-villas.vercel.app/?ci=2026-11-10&co=2026-11-12&br=3&gu=6&ref=OUTO-2026-1234` | 頁面讀網址參數預填日期、房數、人數、Outo 訂單編號（約半天） |
| 2 回填 | TC 在頁面按「複製到 OMS」，產生 JSON 或一行文字（slug、名稱、日期、房數、公告價、佣金率、淨價、訂金、餘款日） | 頁面加按鈕（半天）；OMS 端解析 |
| 3 資料 API | 把 `pub.js`、`pubav.js`、AVAIL_URL 的 JSON 直接給 OMS 讀（都是靜態 JSON，無需認證） | 無；OMS 端自行計算房況 |
| 4 訂單同步 | 訂房信寄出時同時 POST 一筆到 OMS（需 OMS 提供端點與認證） | 頁面加一個 fetch（半天） |
