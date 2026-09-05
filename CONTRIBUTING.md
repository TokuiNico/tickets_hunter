# Contributing to Tickets Hunter

歡迎參與 Tickets Hunter 專案！請閱讀以下指南後再提交你的貢獻。

## 重要提醒

- 本專案僅供教育和研究用途
- 使用者需自行承擔法律責任
- 禁止用於商業牟利或違法用途
- 遵守各票務平台的使用條款

## 開發策略

本專案使用 **zendriver**（nodriver 的活躍 fork，支援 Chrome 145+）作為唯一搶票引擎。平台邏輯已拆分至 `src/platforms/` 目錄，各平台一個模組。

## 貢獻流程

### 1. Fork 與設定

```bash
# Fork 此倉庫後 clone
git clone https://github.com/YOUR_USERNAME/tickets_hunter.git
cd tickets_hunter

# 設定上游倉庫
git remote add upstream https://github.com/bouob/tickets_hunter.git

# 安裝 uv（https://docs.astral.sh/uv/），然後建立開發環境
uv sync                      # 依 uv.lock 建立 .venv（含 pytest / ruff / playwright）
uv run pre-commit install    # 選用：commit 前自動跑 ruff 與 emoji 檢查
```

> 不想用 uv？`pip install -r requirement.txt` 仍可安裝執行期套件，
> 但 `requirement.txt` 是由 `uv.lock` 匯出的，請勿手動編輯。

### 2. 建立分支

```bash
# 同步最新版本
git fetch upstream
git checkout main
git merge upstream/main

# 建立功能分支
git checkout -b feature/your-feature-name
```

**分支命名規則：**

| 前綴 | 用途 |
|------|------|
| `feature/` | 新功能 |
| `fix/` | Bug 修復 |
| `docs/` | 文件更新 |
| `refactor/` | 程式碼重構 |

### 3. Commit 規範

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式（**不含 emoji**）：

```
<type>(<scope>): <description>
```

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | Bug 修復 |
| `docs` | 文件更新 |
| `refactor` | 程式碼重構 |
| `perf` | 效能改善 |
| `chore` | 維護工作 |
| `test` | 測試 |
| `style` | UI/樣式 |

**範例：**
```
feat(kktix): add zendriver area auto select
fix(tixcraft): fix OCR captcha overwriting user input
refactor(fansigo): consolidate tracker blocking into global block list
```

### 4. 提交 Pull Request

```bash
# 推送到你的 fork
git push origin feature/your-feature-name
```

然後在 GitHub 上建立 Pull Request 到 `main` 分支。

**PR 檢查清單：**

- [ ] `make check` 通過（ruff、單元測試、emoji 檢查；CI 會再跑一次）
- [ ] 新增／修改邏輯有對應的單元測試
- [ ] 已在真實瀏覽器測試變更功能正常
- [ ] 無敏感資訊（密碼、API key 等）

PR 開出後 GitHub Actions 會自動執行 **CI** workflow（lint、Ubuntu／Windows 單元測試、
Playwright e2e、PyInstaller 打包）。所有 job 都綠燈、且 `CI passed` 狀態通過才可合併。

## 程式碼規範

- **Python 版本**：3.11（`.python-version`；uv 會自動下載）
- **相依套件**：只改 `pyproject.toml`，再執行 `make lock`（會同步更新 `uv.lock` 與 `requirement.txt`）
- **Lint**：`ruff`（設定在 `pyproject.toml`）。歷史程式碼只啟用會抓到真實錯誤的規則；新程式請以 `ruff format` 排版
- **Emoji 限制**：`.py` 檔案禁止使用 emoji，`.md` 檔案允許
- **除錯輸出**：使用 `DebugLogger`（`debug = util.create_debug_logger(config_dict)`），禁止 `print()`
- **函數命名**：平台函式使用 `nodriver_{platform}_{function}()` 格式，以 `tab, config_dict` 為首參數

## 測試

| 指令 | 內容 | 何時執行 |
|------|------|----------|
| `make lint` | ruff check、ruff format（tests/benchmarks）、`.py` emoji 檢查 | 每次 commit 前 |
| `make test` | `tests/unit/`：util 純函式、settings 設定檔遷移、settings.py HTTP API（真實 tornado） | 每次 commit 前 |
| `make e2e` | `tests/e2e/`：啟動真實 `settings.py` 子程序 + Playwright Chromium 操作設定頁 | 改到 `settings.py` / `www/` 時 |
| `make bench` | `benchmarks/`：熱路徑微基準 | 改到主迴圈效能相關程式時 |

第一次跑 e2e 前先下載瀏覽器：`make e2e-install`（等同 `uv run playwright install --with-deps chromium`）。
離線環境可用 `TICKETS_HUNTER_E2E_CHROMIUM=/path/to/chrome` 指定既有的 Chromium。

不透過 make 的話，對應指令是 `uv run ruff check .`、`uv run pytest tests/unit`、`uv run pytest tests/e2e`。

### 測試撰寫慣例

- 測試檔放在 `tests/unit/`（預設會跑）或 `tests/e2e/`（需手動指定路徑），`src/` 已在 `pythonpath`，直接 `import util`。
- 需要讀寫 `settings.json`／狀態檔的測試請使用 `app_root` fixture，它會把 `TICKETS_HUNTER_APP_ROOT` 指到暫存目錄，不會弄髒 `src/`。
- 需要打 HTTP API 的測試請使用 `settings_server` fixture（真實 `settings.make_app()`，隨機 port）。
- 平台模組（`src/platforms/*`）需要真實票務網站，目前不在自動化測試範圍；請以手動流程驗證：

```bash
cd src
uv run python nodriver_tixcraft.py --input settings.json
```

確認：瀏覽器正常啟動、Console 無錯誤。

## 問題回報

透過 [GitHub Issues](https://github.com/bouob/tickets_hunter/issues) 回報，請附上：

- 作業系統、Python 版本、Chrome 版本
- 重現步驟與錯誤訊息
- 相關螢幕截圖

## 致謝

- **@bouob** - 專案維護者
- **max32002/tixcraft_bot** - 原始專案啟發
- 所有貢獻者與 issue 回報者
