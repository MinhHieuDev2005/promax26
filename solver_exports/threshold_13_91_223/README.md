# Export các solver đạt từ 13/91/223

Gói này chứa các executable độc lập được dùng bởi những lần chạy đạt ngưỡng.

## Chạy nhanh

Các solver ALNS/LNS dùng executable lõi:

```powershell
.\bin\hexudon.exe plan alns < input.json
.\bin\hexudon.exe plan lns < input.json
```

Các solver Chokudai v2 nhận một JSON `op=plan` qua stdin:

```powershell
Get-Content -Raw input.json | .\bin\chokudai_v2_h17_runner.exe
```

Hoặc dùng launcher thống nhất:

```powershell
python .\run_solver.py --solver h17 --input input.json --output result.json
python .\run_solver.py --solver alns --input input.json --output result.json
```

## Tích hợp GUI

Trong `gui.py`, bấm **+ Thêm solver EXE**, chọn executable và trả lời
**Không** khi được hỏi có phải Bot HTTP hay không. Đây là **Runner JSON**.
GUI hiện truyền `history`, `planner_state` và ngân sách tìm kiếm giữa các ngày.
Nếu GUI được mở lại giữa trận, bản H17 mới có thể bắt đầu từ trạng thái server
hiện tại với dự báo traffic quá khứ trung tính. Giữ GUI mở vẫn cho kết quả tốt
hơn vì runner giữ được action và traffic chính xác của các ngày trước.

`revision` trả về từ API `/answer` chỉ là số lần sửa câu trả lời của **cùng
ngày**, không phải số ngày hoàn thành. GUI chỉ commit một plan vào runner history
khi `/status.currentDay` thực sự tăng; nộp lại trong cùng ngày chỉ thay pending
plan và không làm history tiến lên.

Với lựa chọn 20/40/60 giây, GUI bật `exhaustBudget`, dùng slice 1 giây và
32 attempts. Nhánh có upper bound bằng incumbent vẫn được tìm tiếp để đa dạng
endpoint/traffic. Ngày cấu hình 60 giây dùng khoảng 55 giây tìm kiếm giống nhau,
chừa 5 giây cố định cho khởi động process, validate JSON và nộp HTTP. Đây là
giới hạn an toàn; nếu `endsAt` thực tế còn ít hơn thì deadline server vẫn được
ưu tiên.

`input.json` phải chứa `config`, `types`, `history`, `day_info` và tùy chọn
`search`. Với v2, ngân sách hợp lệ là 1..60000 ms. Ví dụ cấu hình H17:

```json
{"timeLimitMs":60000,"sliceMs":1000,"layerCapacity":24,"attempts":6,"randomSeed":1}
```

## Biến thể nên thử

- `h17`: build tương thích GUI/resume mới nhất, phát triển từ bản đạt 225.
- `chokudai_v2_h17_historical_225.exe`: artifact lịch sử chính xác đạt 225;
  không dùng để resume sau khi GUI đã bị đóng.
- `h08`: cũng đạt 225 nhưng lần đo có ngày vượt deadline ngoài tiến trình.
- `alns`: baseline nhanh 3 giây, đạt 224.
- `v2`, `h04`, `h20`, `h22`: các ablation/biến thể nghiên cứu.
- `lns`: baseline 3 giây, đạt 223.

Chi tiết mọi lần chạy nằm trong `manifest.json`. Các run suffix (`h09d3`,
`h09d5`, `h20d3`) phụ thuộc trạng thái checkpoint giữa trận, không phải solver
khởi chạy độc lập từ ngày đầu.

## Lưu ý về mã nguồn

`source/chokudai_v2` là mã nguồn mới nhất của nhánh v2. Các executable H04,
H08 và H17 được giữ nguyên từ thời điểm build thử nghiệm, nên chúng là artifact
chính xác hơn mã nguồn mới nhất khi cần tái hiện kết quả lịch sử. Repository
không lưu commit/snapshot mã nguồn riêng cho từng H04/H08/H17.

`source/legacy` chứa bản sao mã lõi dùng để build `hexudon.exe`, ALNS và LNS.
Thư mục `source` đồng thời giữ đúng layout CMake của repository, có thể build:

```powershell
cmake -S source/solvers/chokudai_v2 -B build -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build --config Release
```

Không có dữ liệu test Q06, tọa độ hay action được hard-code trong solver.
