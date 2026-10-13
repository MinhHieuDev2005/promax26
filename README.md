# hexa-udon

高専プロコン 2026 競技部門「ヘキサうどん」の C++20 クライアントです。公式 API との通信・Session の保存と復旧は o-udon の実装、種別決めと毎日の計画は solver（補給の時期と場所も計画に入れる LNS ＋ 焼きなまし）で行います。

## GUI cục bộ (tiếng Việt)

### Bản cài riêng trên máy Windows này

- Ubuntu riêng tên `HexaUdon`, lưu tại `D:\WSL\HexaUdon`; không đổi cấu hình Docker/WSL chung.
- Nhấp đúp `Open-HexaUdon.cmd` để mở GUI. Nhập URL/token rồi kiểm tra kết nối trước.
  Launcher dành cho dự án ở `D:\30013-o-udon`, binary ở `/home/hexa/build-release/hexa_udon`.
  Giữ cửa sổ launcher mở (có thể thu nhỏ) trong khi chơi để WSL tiếp tục hoạt động.
- Launcher chạy bằng tài khoản Linux không có quyền quản trị `hexa`, giới hạn cả GUI/client
  tối đa 3 GiB RAM, 512 MiB swap và hai CPU logic. Solver dùng hai luồng.
  Đây là giới hạn của tiến trình trò chơi, không phải toàn bộ bộ nhớ WSL.
  Chế độ nhẹ có thể tìm lời giải kém hơn chế độ dùng nhiều CPU.
- Nhấp đúp `Stop-HexaUdon.cmd` và xác nhận để tắt riêng Ubuntu này khi chơi xong.
  Đóng tab không tắt backend. Dừng giữa lúc POST có thể làm kết quả gửi không rõ ràng.
- GUI không được cấu hình tự chạy khi khởi động Windows. Bấm mở lần sau sẽ chạy lại.

**Gỡ sau khi không dùng:** dừng game trước. Nếu cần giữ phiên/log, sao chép
`\\wsl.localhost\HexaUdon\home\hexa\.hexa-udon-gui` ra thư mục Windows trước khi gỡ.
Sau đó chạy trong PowerShell:

```powershell
wsl --unregister HexaUdon
```

**Lệnh trên xóa vĩnh viễn Ubuntu HexaUdon, binary và dữ liệu bên trong nó.**
Không chạy với tên `docker-desktop`. Mã nguồn tại `D:\30013-o-udon` vẫn được giữ lại.

### Chạy thủ công

GUI có nút kiểm tra kết nối, chạy thử, chạy thật, dừng và xem trạng thái phiên.
Không cần cài thư viện Python ngoài. Trên Windows, chạy backend trong **Ubuntu/WSL**,
không chạy client C++ trực tiếp bằng PowerShell.

Sau khi build `build-release/hexa_udon` theo phần bên dưới, chạy trong thư mục dự án:

```bash
python3 gui.py
```

Mở `http://127.0.0.1:8765` trong trình duyệt Windows, nhập URL máy chủ và token của
ban tổ chức. Chọn **Kiểm tra kết nối**, rồi **Chạy thử** trước khi **Chạy thật**.
Chạy thật yêu cầu xác nhận và sẽ POST bài thi; chạy thử vẫn kết nối mạng và gửi token.
Token bị xóa khỏi ô nhập sau khi bắt đầu, nên cần nhập lại cho lần chạy kế tiếp.

- GUI chỉ lắng nghe loopback; không public, proxy hay mở cổng ra LAN/Internet.
- GUI không ghi token xuống tệp, không dùng browser storage và che token trong log hiển thị.
  Client C++ vẫn tạo session/log của riêng nó. Chỉ dùng máy chủ đáng tin cậy; HTTP không mã hóa token.
- Mỗi lần chạy dùng thư mục riêng trong `~/.hexa-udon-gui/`, không ghi đè phiên cũ.
  GUI chỉ nhớ đường dẫn phiên gần nhất trong lần mở hiện tại. Sau khi mở lại GUI,
  dùng CLI `show-state --session-dir PATH` để kiểm tra phiên cũ.
- Đóng tab không dừng client. Nút **Dừng** hoặc Ctrl+C tại terminal GUI sẽ dừng client;
  có thể không xác định được kết quả POST đang gửi. Nếu thấy `RecoveryRequired`,
  không tự chạy lại: kiểm tra trạng thái phiên và trạng thái trên máy chủ trước.
- Không chạy thêm một GUI/client khác cho cùng trận. Giới hạn một tiến trình chỉ áp dụng
  trong một backend GUI. Chưa có tự động phục hồi, quản lý nhiều trận hoặc LAN worker.
- Nếu binary nằm nơi khác: `python3 gui.py --binary ./build/hexa_udon`.
  Nếu cổng bận: `python3 gui.py --port 8766`.
- Kiểm thử GUI (không kết nối máy chủ thi đấu): `python3 -B tests/gui_check.py`.

## 1. ビルド

必要なもの: C++20 対応コンパイラ（GCC 13 で確認）、CMake 3.20 以上、nlohmann_json 3.11.3 以上、libcurl。

```bash
# Ubuntu / WSL
sudo apt install -y cmake nlohmann-json3-dev libcurl4-openssl-dev
```

```bash
cmake -S . -B build-release -DCMAKE_BUILD_TYPE=Release -DBUILD_TESTING=ON
cmake --build build-release --parallel 4
ctest --test-dir build-release --output-on-failure
```

## 2. 実行

token と URL は環境変数で渡し、README や Git に実値を書きません。

```bash
export VENUE_BASE_URL='https://<venue-host>'
export PROCON_TOKEN='<official-token>'
```

接続を確認する:

```bash
./build-release/hexa_udon check --base-url "$VENUE_BASE_URL" --token-env PROCON_TOKEN
```

試合に出る（`--execute` を付けたときだけ POST します。付けなければ dry-run）:

```bash
./build-release/hexa_udon auto \
  --base-url "$VENUE_BASE_URL" --token-env PROCON_TOKEN --execute \
  --session-dir /secure/runtime/session --log-dir /secure/runtime/log
```

練習場（procon37arena.online）では `practice.sh` が build・待機・Session の退避・`auto --execute` をまとめて行います。

### 本番運用の方針

本番当日の時系列手順、確認項目、異常時の判断は [docs/cheatsheet.md](docs/cheatsheet.md) を参照してください。標準・推奨構成は主 PC 単体での実行です。LAN worker は、事前に `worker-preflight` と実際の試合を最後まで安定して確認できた場合だけ使用します。

LAN worker を使う場合は、主 PC と全 worker を clean worktree かつ同じ commit に揃えてください。build fingerprint は git commit 由来で未commit差分を識別しないため、dirty worktree のままでは worker 構成の同一性を検証できません。worker の詳細な OS 別設定、network、preflight 手順は [docs/lan-worker.md](docs/lan-worker.md) を参照してください。

本番では、`--execute` がなければ POST されません。開始待ちの403が続く環境では `--max-get-retries 200` を推奨します。本番runごとに新しい session/log directory を使い、`waiting-for-match` は正常状態として停止しないでください。`RecoveryRequired` または POST 結果不明になった場合は、同じ session directory で自動再実行せず、公式状態と `show-state` を確認してから復旧手順を判断します。

公式接続情報は主 PC だけに置き、token と worker secret を Git、チャット、コマンド履歴、スクリーンショットに残さないでください。worker は公式 token/API を使わず、worker 専用 secret で主 PC と通信します。

### 1 試合の流れ

1. `GET /setting` を受け取ったら、solver が種別（どの車を補給車にするか）を決めて `POST /agent` します。
   開始前の予算の 50% を種別決めに使い、残りを day0 precompute に回します（`--kind-ms` で上書きできます）。実際の配分は実装で変わる可能性があるため、CLI ログの `budgetMs` で確認してください。
2. 種別を出したら、締切（startsAt が分かればその時刻）まで別のスレッドで 1 日目を計画しておきます。1 日目の道路は全部空いていて、朝の状態も種別で決まるためです。1 日目はこの解から始めるので、1 日目の最初の提出から良い計画を出せます（回答時間が短くなる）。途中から入り直したときはしません。
3. 毎日、まず全員が待つ計画を出します（計画ができるまでの保険）。
4. solver が日の締切の `--safety-seconds`（既定 3 秒）前までの残り時間の 85% で計画し、系列・玉・翌日に効く項が良くなるたびに `--interim-ms`（既定 3000）ごとに出し直します。最後の計画が直前に出したものと同じなら出し直しません（回答時間で負けないため）。
   1 日の計画は、乱数の種だけを変えた焼きなましを `--threads` 本同時に回し、一番良い解を使います。`--threads` は日次solverだけでなく、種別決め中の候補のSA探索にも使われます。
5. 提出する計画はすべて、提出の前に solver のシミュレーター（公式ルールの再現）で確かめます。

内部のheuristic scoreと、公式順位用の `OfficialScore` は別物です。`OfficialScore` は「総系列数 → 日別系列数の合計 → 玉数」の辞書順で比較します。そのため、heuristicだけが小さく改善しても solver-interim は POST せず、strict simulatorで計算した `OfficialScore` が直近に受理された計画より辞書順で厳密に改善した場合だけ POST します。最終日は翌日の価値と、継続用の燃料・終点評価を使いません。種別決めでは通常道路と混雑道路の両条件を見て、翌日の道路状態も計画評価に反映します。

### 主な option

| option | 意味 |
| --- | --- |
| `--execute` | POST する（無ければ dry-run） |
| `--types 0,0,0,1` | 種別を手で指定する（solver の種別決めをしない） |
| `--kind-ms N` | 種別決めの持ち時間（既定: 締切から自動） |
| `--interim-ms N` | 良くなった計画を出し直す間隔。0 なら最後の計画だけ |
| `--safety-seconds N` | 日の締切の何秒前までに提出を終えるか（既定 3） |
| `--threads N` | 日次solverと種別決め中の候補SA探索を同時に回すスレッドの数（既定: 論理スレッド数の半分。全部使うと通信や OS の処理が遅れるため） |
| `--max-get-retries N` | `/setting` や日次状態のGET再試行回数（既定 8）。練習場など開始待ちで403が続く環境では 200 を推奨 |
| `--lan-worker-timeout-ms N` | LAN worker の応答待ち上限。指定可能範囲などの詳細は [docs/lan-worker.md](docs/lan-worker.md) を参照 |
| `--seed N` | LAN worker に渡す乱数の種のもと |
| `--session-dir DIR` / `--log-dir DIR` | Session と OperationLog の置き場所（既定 `run/session`, `run/log`） |

`hexa_udon --help` で全 option を表示します。

## 3. LAN worker（任意）

別の PC（または同じ PC の別プロセス）で solver を乱数の種を変えて回し、主 PC の計画より公式の点（総系列 → 日別系列 → 玉）が高ければそれを使います。worker は公式 API・token に触れず、worker 専用 secret で loopback / private LAN だけで通信します。

```bash
export HEXA_LAN_WORKER_SECRET='<worker-only-secret>'
# worker
./build-release/hexa_udon worker --listen 127.0.0.1:39001 --worker-token-env HEXA_LAN_WORKER_SECRET \
  --worker-index 0 --worker-count 1
# 起動を確かめる
./build-release/hexa_udon worker-preflight --listen 127.0.0.1:39001 --worker-token-env HEXA_LAN_WORKER_SECRET \
  --worker-index 0 --worker-count 1
# 主 PC
./build-release/hexa_udon auto --base-url "$VENUE_BASE_URL" --token-env PROCON_TOKEN --execute \
  --lan-worker 127.0.0.1:39001
```

worker は日の締切の 1 秒前（`--lan-worker-timeout-ms` で上限を指定可）まで、自分の `--threads` 本で計画します。返ってきた計画は、依頼と同じ条件で解いたか（requestId、入力、盤、乱数の種、build、点など）を照合し、主 PC のシミュレーターで確かめてから比べます。照合に失敗した・時間切れの worker は使いません。

複数の PC をつなぐ手順（Windows は WSL、Mac、ネットワークとファイアウォールの設定）は [docs/lan-worker.md](docs/lan-worker.md)、よく使うコマンドは [docs/cheatsheet.md](docs/cheatsheet.md) にまとめています。

## 4. 異常時と復旧

- POST の前に失敗した提出は `submissionAttempted=false`、POST したが結果が分からないものは `null` として Session に残し、`null` が出たら `RecoveryRequired` で止まります（自動で送り直しません）。
- `RecoveryRequired` のあとは同じ Session で `auto` を再実行せず、`show-state` と公式の状態を照らし合わせてから `recover`（既定は dry-run）を使います。

```bash
./build-release/hexa_udon show-state --session-dir /secure/runtime/session
./build-release/hexa_udon recover --base-url "$VENUE_BASE_URL" --token-env PROCON_TOKEN \
  --session-dir /secure/runtime/session --log-dir /secure/runtime/log
```

- Session / log / token / secret / build 成果物は Git に入れません。Session と log の directory は 0700、ファイルは 0600 で作ります。

## 5. 実装の場所

| 領域 | 場所 |
| --- | --- |
| solver の型と宣言 | `include/hexa_udon/solver.hpp` |
| 問題（大域変数）と o-udon の型との変換 | `src/core/problem.cpp` |
| 1 日のシミュレーション（公式ルールの再現） | `src/simulator/simulator.cpp` |
| 最短経路（最速 / 燃料最小） | `src/pathfinding/router.cpp` |
| 1 日の解（訪問の並びと補給）の組み立てと評価 | `src/planner/day_planner.cpp` |
| 1 日の計画（LNS ＋ 焼きなまし） | `src/optimizer/optimizer.cpp` |
| 種別決め | `src/planner/prematch_type_selector.cpp` |
| 試合の流れ・提出・LAN worker の採否 | `src/app/auto_client.cpp` |
| LAN worker | `src/app/lan_worker.cpp` |
| HTTP・rate limit・Retry-After | `src/protocol/` |
| Session・Recovery・polling・永続化 | `src/session/` |
# Agent selection

The prematch selector uses strict score ordering. Candidates
are evaluated sequentially with the remaining time shared among untested
lineups. Each runs normal and congested-road simulations: brand counts use
the worse result, bowl counts use the sum. Lineups are ranked lexicographically
by match brands, daily brands, then bowls. Supply count never overrides score;
exact ties retain the first evaluated lineup.
There is no top-three screening or repeated-seed median stage.

The HAUI client window, half-budget selection (about 28.5 seconds when the
full window remains), day-zero preplanning, 8-thread GUI configuration and
submission behavior are unchanged. Initialization can overrun the budget;
this is not a hard real-time guarantee. HAUI score gains remain unverified.
