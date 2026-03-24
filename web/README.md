# Bitget Wallet 網頁介面

用瀏覽器操作「Token 價格」、「安全檢查」、「Swap 報價」，後端會呼叫專案裡的 `scripts/bitget_api.py`。

## 啟動方式

在專案根目錄執行：

```bash
pip install -r web/requirements.txt   # 首次需要
python3 web/server.py
```

瀏覽器開啟：**http://127.0.0.1:5051**

（若 5051 被佔用，可設環境變數：`PORT=8080 python3 web/server.py`）

## 功能

| 區塊 | 說明 |
|------|------|
| **Token 價格** | 選鏈、填合約（原生代幣留空），查即時價格 |
| **連接錢包（EVM）** | 優先 `window.bitkeep.ethereum`（Bitget Wallet 擴充），否則 `window.ethereum`；可讀主幣餘額、一鍵帶入半自動 Swap 地址與 PnL 數量 |
| **持倉 PnL 試算** | 手動輸入數量與平均買入價（USD），按「更新行情」用 API 現價算損益；資料存瀏覽器 localStorage（非交易所官方 PnL，黑客松請以主辦規則為準） |
| **安全檢查** | 輸入鏈 + 合約地址，查看審計結果與風險 |
| **Swap 報價** | 輸入從/到鏈與合約、數量，取得預估可換數量（原生幣「從合約」可留空） |
| **同鏈 Calldata + 錢包** | EVM 同鏈：報價 → `swap-calldata` → 已連接錢包 `eth_sendTransaction` 簽名送出 |
| **半自動 Order** | 含 **④ 查詢訂單狀態**（`order-status`） |

資料皆來自 Bitget Wallet API，本機不儲存私鑰或敏感資料。
