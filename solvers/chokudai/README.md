# Chokudai repair solver — độc lập với solver cũ

Solver C++ mới dùng **ALNS seed + bounded Chokudai ruin/recreate**. Không sửa
`src/*.cpp`, header lõi, `gui.py`, CMake gốc hay executable cũ. CMake con chỉ
biên dịch lại và liên kết với lõi hiện có để tái sử dụng routing, decoder và
simulator. Đây là thuật toán thử nghiệm, chưa phải solver được chứng minh mạnh
hơn ALNS trên mọi bản đồ.

## Thuật toán

1. Tạo nghiệm hợp lệ bằng wait và các greedy hiện có.
2. Dành mặc định 30% ngân sách (tối đa 12 giây) cho một ALNS seed.
3. Dựng graph nhiều phương án thời gian/nhiên liệu và cache rendezvous.
4. Sinh các root bằng cách bỏ 1–6 visit khỏi nghiệm tốt nhất.
5. Mỗi độ sâu có một hàng đợi ưu tiên tồn tại qua nhiều lượt. Mỗi lượt mở rộng
   một node của mỗi tầng; các node chưa mở rộng ở tầng trước vẫn được giữ.
   Đây là Chokudai trên **quyết định sửa tuyến**, không phải beam chỉ đi một lần
   qua từng tầng và không phải tìm đồng thời mọi bước chân của mọi xe.
6. Thử chèn visit trên các patrol/vị trí khác nhau. 3/4 nhóm ứng viên ưu tiên
   loại còn thiếu và đường vòng ngắn; phần còn lại lấy ngẫu nhiên để đa dạng.
7. Thử decoder ưu tiên thời gian và decoder ưu tiên nhiên liệu/refuel. Mô phỏng
   toàn đội để xử lý chính xác stock, đi ngang spot, thời gian chờ và refuel.
8. Dựng lại skeleton từ acquisition trace thực tế. Visit bị decoder bỏ qua
   không được coi là đã phục vụ và có thể được chèn lại ở nhánh sau.
9. Sau một số expansion, khởi động lại ruin/recreate quanh nghiệm tốt nhất.

Giới hạn bộ nhớ: số node sống tối đa `(depth + 1) * layerCapacity`, cộng tập
chữ ký tối đa 50.000 mục mỗi đợt. Chữ ký chứa tầng và toàn bộ skeleton, không
dùng vị trí cuối ngày làm khóa duy nhất. Các skeleton ở đây là **proposal để
decode lại**, không phải toàn bộ physical state; travel được chọn lại khi mở
rộng. Chặn dung lượng và depth khiến đây là tìm kiếm xấp xỉ, không chứng minh
tối ưu.

## Bảo vệ tiêu chí 1 và 2

Nghiệm được chọn thay thế phải thỏa đồng thời:

```text
distinct_types_new >= distinct_types_best
daily_types_new    >= daily_types_best
```

Sau đó so sánh `(distinct_types, daily_types, servings, patrol_fuel)` theo thứ
tự từ trái sang phải. Khi hai tiêu chí đầu bằng nhau, servings được ưu tiên
trước nhiên liệu. Nghiệm đang khám phá được phép tạm thiếu loại để tìm đường
sửa; chỉ nghiệm qua guard mới có thể trở thành output.

Guard bảo vệ **nghiệm nền và các incumbent của cùng ngày, cùng trạng thái**.
Nó không bảo đảm đủ mọi loại trên map bất khả thi, không bảo đảm thắng một lần
ALNS khác chạy nhiều thời gian hơn, và không bảo đảm độ phủ ngày mai. Phiên bản
này tối ưu ngày hiện tại; tối ưu tổng trận cần đo bằng replay nhiều ngày.

## Build trên Windows/MSYS2 UCRT64

Cần CMake, Ninja, GCC C++20 và Boost.JSON >= 1.81. Trong môi trường kiểm thử đã
cài `mingw-w64-ucrt-x86_64-boost` (kèm boost-libs/ICU) bằng pacman.

```powershell
rtk cmake -S solvers/chokudai -B build/chokudai -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=C:/msys64/ucrt64/bin/g++.exe -DCMAKE_PREFIX_PATH=C:/msys64/ucrt64 -DBUILD_TESTING=OFF
rtk cmake --build build/chokudai --target chokudai_runner chokudai_tests chokudai_benchmark -j 4
rtk proxy ctest --test-dir build/chokudai --output-on-failure
rtk python -X utf8 -m pytest solvers/chokudai/test_protocol.py -q -p no:cacheprovider
```

EXE mới: `build/chokudai/chokudai_runner.exe`. Trên MinGW chương trình được
liên kết static, không cần thay DLL trong `bin/` của các solver cũ.

## Input/output

Đọc một JSON từ stdin; xuất đúng một JSON ở stdout. Log lỗi cũng trả JSON
`{"ok":false,"error":"..."}` và exit code 1.

Native payload:

```json
{
  "op": "plan",
  "config": "cùng object config dùng cho hexudon",
  "day_info": "cùng object day_info; day bắt đầu từ 0",
  "types": [0, 0, 1, 0],
  "history": {
    "distinct_brands": [],
    "submitted_actions": [],
    "cumulative_daily_types": 0,
    "total_servings": 0
  },
  "search": {
    "timeLimitMs": 50000,
    "seedPercent": 30,
    "depth": 6,
    "layerCapacity": 96,
    "branching": 18,
    "randomSeed": 1
  }
}
```

Hai chuỗi mô tả `config` và `day_info` trên phải được thay bằng object thực.
`types` có thể bỏ qua để lấy `kind` từ agents. Nếu thiếu history, solver trả
`history_supplied:false`; caller cần gửi lịch sử thật để đánh giá loại toàn trận.
Không có state lưu ngầm trên đĩa giữa các trận.

Hỗ trợ giao thức GUI EXE hiện có:

- `{"op":"roles","config":...}`: tái sử dụng role selector ALNS, tối đa 2.5s.
- `{"op":"plan","config":...,"state":...}`: `state.day` **bắt đầu từ 1**.
- Output: `{"ok":true,"plan":[...],"diagnostics":{...}}`.
- Dùng `config.spots[].stocks` theo quy tắc simulator hiện tại; không tự suy
  diễn stock giữa ngày từ trạng thái không đầy đủ.

Trong GUI chọn **+ Thêm solver EXE**, trỏ đến EXE mới. Không tự đăng ký hoặc
thay runner mặc định. GUI hiện không truyền `search`/history cho custom runner,
nên tích hợp GUI mặc định dùng **3 giây**. Để thử **50 giây**, dùng native payload
trên hoặc chạy `chokudai_runner.exe --time-ms 50000` qua caller riêng. Cờ CLI
không được GUI tự truyền; không nên nhầm rằng tăng thanh thời gian GUI sẽ đổi
ngân sách bên trong custom runner này.

`endsAt`, nếu có, phải là timestamp Unix giây còn hiệu lực. Solver chừa 500ms
trước endsAt và một phần ngân sách cho trả kết quả. Giới hạn 50s là deadline
hợp tác: mỗi lần gọi preprocessing/decoder lõi là không ngắt giữa chừng được.
Caller cần timeout process riêng; benchmark ghi thời gian thực tế.

## Benchmark

```powershell
rtk proxy build/chokudai/chokudai_benchmark.exe cases/mlns-profile/online/q01-d2d87157.json 3000 3 build/chokudai/benchmark-q01-3s.json
rtk proxy build/chokudai/chokudai_benchmark.exe cases/mlns-profile/online/q06-1cbf1a56.json 50000 1 build/chokudai/benchmark-q06-50s.json
```

Hai solver dùng cùng vai trò cố định và cùng ngân sách mỗi ngày. Baseline là
`plan_day("alns")` đầy đủ, challenger là solver mới. Mỗi solver đi theo quỹ đạo
trận riêng, truyền vị trí/nhiên liệu/history qua các ngày. Traffic chỉ được tạo
từ đội đang mô phỏng; không giả vờ tái tạo hành động đối thủ online.

JSON báo cáo có điểm mỗi ngày, tổng trận, wall time, điểm seed, số expansion,
và cờ không giảm coverage so với baseline. Chạy này không thay thế đánh giá
nhiều seed và nhiều đối thủ. Kết quả đo thực tế được ghi trong `RESULTS.md`.
