# 研究進度追蹤網站（公開模板）

用 AI 每天回答三件事：**上次做到哪、今天做什麼、今天完成了什麼**。
進度寫成 Markdown 檔，由 Python 腳本產生靜態網頁，放在 GitHub Pages。

> 本 repo 的內容全部是**虛構範例**（葉片病害辨識）。真實研究放在另一個結構相同的私有 repo。

## 怎麼用
1. 用 Claude Code（或其他 AI 工具）開啟這個資料夾，AI 會先讀 [CLAUDE.md](CLAUDE.md)。
2. 開工時說「開始今天」，AI 會整理進度並建議今天的工作。
3. 收工時說「今天做了…」，AI 會更新待辦、日誌、實驗紀錄，並重建網頁。

## 手動建置與預覽
```
python3 scripts/build.py
python3 -m http.server -d docs 8000
```
然後打開 http://localhost:8000 。只需要 Python 3，不用安裝任何套件。

## 結構
| 位置 | 內容 |
|---|---|
| `CLAUDE.md` | 給 AI 的規則：格式、流程、網頁風格、擴充方式 |
| `TODO.md` | 待辦清單 |
| `logs/` | 每日日誌 |
| `experiments/` | 實驗紀錄 |
| `scripts/` | 建置程式、模板、樣式 |
| `docs/` | 產生出來的網頁（GitHub Pages 來源） |

## 用在自己的研究
複製這個 repo 並設成私有，刪掉 `logs/`、`experiments/` 裡的範例，清空 `TODO.md` 的項目，就可以開始使用。
