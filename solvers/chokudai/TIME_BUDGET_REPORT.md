# Ngân sách thời gian cho Chokudai v1

Ngày đo: 29/09/2026. Đánh giá **EXE v1 hiện có**, không sửa thuật toán, tham số mặc
định, GUI hay solver cũ.

## Kết luận

**Đề xuất 20 giây/lần lập kế hoạch làm mức cân bằng cho v1 hiện tại.**
Không có bằng chứng rằng đặt 50 giây mặc định luôn cho kết quả tốt hơn.

- Ngày đầu của bốn map: 5–50 giây đạt cùng tổng 100 udon; 3 giây đạt 99.
- Trạng thái khó hơn, Q06 ngày thứ 3: 20 giây đạt 35 udon ở cả hai seed;
  50 giây đạt 36 và 34, trung bình cũng là 35.
- 50 giây có **điểm cao nhất quan sát được** ở trạng thái đó, nhưng không phải
  **mức ngân sách có kết quả tốt nhất một cách ổn định**.
- Toàn trận Q06, 7 ngày: 20s đạt **13 / 91 / 222**, 50s đạt **13 / 91 / 223**.
  Thêm khoảng 210 giây tổng thời gian giải để lấy thêm 1 udon, tức khoảng 0,45%.
- Mọi trạng thái đã đo đều giữ đủ số loại của map trong ngày. Đây là kết quả
  thực nghiệm trên mẫu, không phải chứng minh solver luôn bảo đảm điều này.

Nếu chỉ xét các trạng thái ngày đầu, 5 giây là mốc hiệu quả nhất. Khuyến nghị
20 giây dành thêm thời gian cho ngày sau, khi vị trí, nhiên liệu và traffic
khác ngày đầu; không khẳng định 20 giây là tối ưu toán học hay áp dụng cho mọi map.

Chọn thực dụng: **5s để thử nhanh**, **20s làm mặc định cân bằng**, **50s khi ưu
tiên điểm cao nhất quan sát được và chấp nhận chi phí thời gian**. 20s không có
điểm tuyệt đối cao nhất trong lượt toàn trận; nó đạt khoảng 99,55% điểm của 50s
với 40% ngân sách danh nghĩa. Chưa đủ dữ liệu để khuyến nghị riêng 30s hoặc 40s.

## Thiết kế phép đo

- CPU: AMD Ryzen 7 8745H, 8 nhân / 16 luồng logic; Windows, bản Release.
- `HEXUDON_THREADS=4`, tối đa hai process solver đồng thời. Không đồng nhất điều
  kiện này với chạy GUI mặc định, nơi lõi có thể dùng tới 8 worker.
- Giữ nguyên `seedPercent=30`, `depth=6`, `layerCapacity=96`, `branching=18`.
- Chọn vai trò một lần cho mỗi map, rồi đóng băng. Q01 `[0,0,1,0]`,
  Q03 `[0,1,0,1,0,0]`, Q04 `[0,1,0]`, Q06 `[0,0,1]`.
- Ngày đầu được đóng băng cùng vị trí, nhiên liệu, stock, traffic, lịch sử.
  Snapshot ngày thứ 3 được tạo bằng hai ngày rollout v1, 3 giây/ngày, seed 1.
  Mọi ngân sách ở cùng snapshot nhận **chính xác cùng input**.
- Các lượt được xáo thứ tự cố định. Mỗi plan được phát lại bằng simulator lõi;
  điểm thực tế phải trùng `diagnostics.score`.
- Traffic là mô hình một đội: tổng lượt lưu lại trên đường trong hai ngày gần
  nhất, chia cho một đội. Không mô phỏng đối thủ hoặc đầy đủ môi trường online.
- Ngân sách tính cho **một ngày/lần gọi plan**, không phải toàn trận; không gồm
  chọn vai trò, replay kiểm chứng hoặc thời gian truyền mạng.

Điểm được đọc theo thứ tự: **loại toàn trận đã thu / loại trong ngày / udon**.
Trong rollout toàn trận, tiêu chí 2 là tổng số loại thu được của từng ngày.
Không đánh đổi giảm hai tiêu chí đầu để lấy thêm udon.

## 1. Quét ngày đầu: 28 lượt

Một seed, bốn map, bảy mức thời gian. Các ô là số udon.

| Ngân sách | Q01 | Q03 | Q04 | Q06 | Tổng | Wall time trung bình/lượt |
|---|---:|---:|---:|---:|---:|---:|
| 3s | 18 | 33 | 12 | 36 | 99 | 2,878s |
| 5s | 18 | 34 | 12 | 36 | 100 | 4,772s |
| 10s | 18 | 34 | 12 | 36 | 100 | 9,764s |
| 20s | 18 | 34 | 12 | 36 | 100 | 19,779s |
| 30s | 18 | 34 | 12 | 36 | 100 | 29,769s |
| 40s | 18 | 34 | 12 | 36 | 100 | 39,778s |
| 50s | 18 | 34 | 12 | 36 | 100 | 49,764s |

Tất cả các lượt lần lượt đạt đủ **4 / 10 / 3 / 13 loại** ở Q01/Q03/Q04/Q06.
Tổng udon chỉ là thống kê trên cùng bộ mẫu, không phải điểm của một trận.

Từ 5s đến 50s, thời gian danh nghĩa tăng 10 lần nhưng không thêm udon trong
nhóm ngày đầu này. Vì vậy không thể chọn 50s chỉ dựa trên lập luận tìm lâu hơn.

## 2. Ngày thứ 3: 15 lượt bổ sung

Q03: seed 1 ở 5s, 10s, 20s, 50s đều đạt **10 / 10 / 34**.

Q06: mọi ô đều đạt **13 / 13 loại**; bảng dưới là udon trên cùng snapshot.

| Ngân sách | Seed 1 | Seed 2 | Trung bình hai seed |
|---|---:|---:|---:|
| 5s | 35 | Chưa đo | — |
| 10s | 34 | 34 | 34,0 |
| 20s | 35 | 35 | 35,0 |
| 30s | 34 | 35 | 34,5 |
| 40s | 34 | 35 | 34,5 |
| 50s | 36 | 34 | 35,0 |

20s cải thiện 1 udon so với 10s ở cả hai seed. Tăng từ 20s lên 50s tốn thêm
30s/lượt nhưng không tăng trung bình của hai seed này. Tuy nhiên, **hai seed
là mẫu nhỏ**, chưa đủ ước lượng chắc chắn tỷ lệ thắng hoặc phân vị điểm.
5s cũng đạt 35 ở seed 1, nên chưa thể khẳng định 20s vượt 5s một cách tổng quát.

## 3. Đối chiếu toàn trận Q06: 14 lượt lập kế hoạch

Hai rollout cùng snapshot ngày đầu và cùng seed 1, sau đó mỗi bên tự cập nhật
vị trí, nhiên liệu, history và traffic theo kế hoạch đã thực hiện.
Không ép ngày sau về cùng snapshot, vì cần đo hệ quả của đường đi ngày trước.

| Ngày | 20s/ngày: udon | 50s/ngày: udon | Số loại mỗi bên |
|---|---:|---:|---:|
| 1 | 36 | 36 | 13 |
| 2 | 31 | 32 | 13 |
| 3 | 35 | 36 | 13 |
| 4 | 28 | 27 | 13 |
| 5 | 30 | 31 | 13 |
| 6 | 24 | 23 | 13 |
| 7 | 38 | 38 | 13 |
| **Tổng** | **222** | **223** | **91 lượt loại/ngày** |

Cả hai đều đạt 13 loại toàn trận và 13 loại trong từng ngày: không có khác biệt
hai tiêu chí ưu tiên trong lượt đo này.

- Tổng wall time của các lần gọi solver: **138,458s** ở mức 20s và **348,445s**
  ở mức 50s. Đây là tổng thời gian từng process, không phải thời gian chờ của
  batch hai process chạy song song.
- Chênh lệch: **+1 udon / +209,987s**. Đây là lý do chọn 20s cho hiệu quả thời gian,
  không phải khẳng định 20s thắng điểm 50s.
- Chokudai có tác dụng trực tiếp trong rollout: ở 20s, một ngày tăng 27 → 28 sau
  seed; ở 50s, năm ngày tăng sau seed, tổng cộng +6 udon trên các trạng thái đó.
  Không được diễn giải +6 này thành mức thắng so với rollout 20s, vì các ngày
  có vị trí/nhiên liệu và seed khác nhau. Mức thắng toàn trận thực đo chỉ là +1.

Tổng cộng **57 lần lập kế hoạch được đánh giá**: 43 trên snapshot và 14 trong
hai rollout toàn trận; chưa tính các lượt tạo snapshot và kiểm tra giao thức.

## 4. Vì sao thêm thời gian chưa mang lại nhiều điểm?

### Thay ngân sách không chỉ kéo dài cùng một lần tìm kiếm

V1 tạo ALNS seed với giới hạn:

```text
seed_time = min(12.000 ms, 30% × total_time)
```

ALNS dùng tiến độ thời gian để điều chỉnh nhiệt độ simulated annealing
(`src/lns.cpp`, đoạn tính `elapsed / alns_budget_ms`). Thay ngân sách làm đổi
lịch nhiệt, quyết định chấp nhận và nhánh tìm kiếm. Lịch chạy của CPU cũng ảnh
hưởng số vòng lặp trong một khoảng thời gian.

Do đó, cùng seed ngẫu nhiên nhưng ngân sách khác **không** đồng nghĩa chạy tiếp
nghiệm của lần ngắn hơn. Guard chỉ bảo vệ incumbent **bên trong một lần gọi**,
không bảo đảm lần gọi 50s tốt hơn lần gọi 20s.

### Phần tìm kiếm sau seed ít cải thiện servings trên các snapshot này

Trong 43 lượt trạng thái cố định, chỉ Q03 ngày đầu ở 10s có thêm udon sau seed:
**33 → 34**. Các lượt còn lại có servings cuối bằng servings của seed; vẫn có
thể cải thiện tie-break nhiên liệu mà bảng ba tiêu chí không thể hiện.

Q06 ngày đầu: 3s mở rộng 1.053 node, 50s mở rộng 19.252 node, nhưng cả hai vẫn
được 36 udon. Q04 tương ứng 8.138 và 161.253 node, vẫn được 12 udon.
Như vậy search vẫn chạy; thêm expansion chưa chuyển thành thêm udon ở các mẫu này.

Đặc biệt, từ 40s trở lên ALNS seed đã chạm trần 12s. Tăng 40 → 50s chỉ kéo dài
pha sau seed. Điểm seed khác nhau giữa hai lần vẫn có thể do timed search;
không được quy mọi chênh lệch điểm cho phần Chokudai tăng thêm.

## Giới hạn kết luận

- Chỉ bốn map ngày đầu, hai snapshot giữa trận, hai seed trên một snapshot khó,
  và một cặp rollout toàn trận. Chưa có khoảng tin cậy hoặc kiểm định thống kê.
- Chưa chạy trọn trận ở tất cả bảy ngân sách; vì vậy không chứng minh 20s là
  mốc tốt nhất trong toàn bộ khoảng 3–50s. Đây là lựa chọn thực dụng từ mẫu đo.
- Các lượt không được cô lập/pin CPU; tải hệ thống và thermal throttling có
  thể ảnh hưởng timed search. Khi một process xong sớm, process kia chạy một mình.
- Vai trò và tham số search được giữ cố định, không tối ưu lại theo từng ngân sách.
  Kết quả không đại diện đầy đủ cho mọi cấu hình vai trò hoặc đối thủ online.
- Guard theo ngày không bảo đảm tối ưu nhiên liệu/vị trí cho cả tương lai.
  Thêm thời gian giải ngày hiện tại không tự biến v1 thành bộ tối ưu nhiều ngày.

## Tái tạo và dữ liệu

Script mới: `budget_sweep.py`; đọc bảng bằng `summarize_budget.py`.

```powershell
rtk python -X utf8 solvers/chokudai/budget_sweep.py --prepare
rtk python -X utf8 solvers/chokudai/budget_sweep.py --states q03-d2 q06-d2 --budgets 5000 10000 20000 50000
rtk python -X utf8 solvers/chokudai/budget_sweep.py --states q06-d2 --budgets 10000 20000 30000 40000 50000 --seeds 1 2
rtk python -X utf8 solvers/chokudai/budget_sweep.py --matches --states q06-d0 --budgets 20000 50000 --jobs 2 --threads 4
rtk python -X utf8 solvers/chokudai/summarize_budget.py
rtk python -X utf8 solvers/chokudai/summarize_budget.py build/chokudai/budget-study/matches.jsonl
```

Raw JSONL và snapshot nằm trong `build/chokudai/budget-study/` (Git ignore).
Script nối thêm kết quả và bỏ qua cặp đã đo. Muốn đo lại độc lập, dùng `--output`
khác và `--prepare`; lưu ý chọn lại roles/tạo lại snapshot sẽ không còn cùng
input với bộ đo này. Muốn so sánh trực tiếp, phải giữ nguyên các snapshot.

Hash Git của executable v1 được đo:
`a08ba90afea581e1900ede44cd6c0298385bbf3c`.
Hash solver.cpp/solver.hpp/main.cpp/EXE/gui.py không đổi trước và sau phép đo.
Bộ kiểm tra giao thức: **14 passed**; hai script benchmark mới qua `py_compile`.

## Áp dụng ngân sách

Với caller hỗ trợ native JSON, đặt `search.timeLimitMs` thành `20000`; hoặc gọi
`chokudai_runner.exe --time-ms 20000` rồi gửi payload vào stdin. Đây là hướng dẫn,
**chưa tự thay đổi mặc định** của v1.

GUI hiện không gửi `search` cho custom runner, nên EXE vẫn dùng mặc định 3s.
Chỉ tăng timeout bên ngoài GUI không làm ngân sách tìm kiếm nội bộ thành 20s.
Khi có `endsAt`, runner còn giới hạn ngân sách theo deadline thực tế.

Nếu muốn dùng hiệu quả 40–50s ở phiên bản sau, đáng thử nhiều seed/restart độc
lập và giữ nghiệm tốt nhất qua guard, hoặc mở rộng quyết định rendezvous/repair.
Đây là hướng thử nghiệm, **chưa được triển khai hoặc chứng minh cải thiện**.
