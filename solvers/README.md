# Thêm hoặc thay solver EXE trong GUI

## Thêm solver mới vào danh sách

1. Mở lại GUI nếu đang chạy phiên bản cũ.
2. Bấm **+ Thêm solver EXE** cạnh danh sách **Solver Thuật toán** (hoặc trong
   tab **Kho Solver & Hướng Dẫn**).
3. Chọn EXE hoặc Python `.py` tin cậy, nhập tên, ví dụ `MySolver`.
4. Chọn kiểu EXE trong hộp thoại: **Có = Bot HTTP**, **Không = Runner JSON**.
5. Mục **HTTP: MySolver** hoặc **EXE: MySolver** xuất hiện và được chọn ngay.

Mỗi EXE có một mục riêng; ACO, ALNS, MLNS, Procon26 và các mục cũ vẫn giữ
nguyên. Runner JSON mới cũng có trong hai danh sách chọn ở Arena 1v1 và tham gia
Auto-Race ALL; không tự thêm đội vào các giải đấu 4/6 đội định sẵn.
Danh sách lưu tại `solvers/registered.json`, mở lại GUI vẫn còn. GUI chỉ lưu
đường dẫn, không sao chép executable: giữ nguyên vị trí EXE, DLL và tài nguyên.
File `.py` chỉ dùng giao thức Runner JSON; Bot HTTP vẫn yêu cầu `.exe`.
File cấu hình này là cục bộ, không đưa vào Git.

Để xóa, chọn mục **EXE: <tên>** hoặc **HTTP: <tên>**, bấm **Xóa solver**
và xác nhận. Thao tác chỉ xóa đăng ký khỏi GUI và cấu hình đã lưu, không xóa
file EXE/DLL. Không xóa được solver có sẵn hoặc đổi danh sách khi đang thi đấu.

Để thay EXE hoặc đổi kiểu của solver đã thêm, làm lại thao tác trên, nhập
đúng tên cũ (không kèm tiền tố EXE:/HTTP:) và xác nhận thay thế. Hoặc đóng
GUI rồi thay EXE tại đường dẫn đã đăng ký. Việc thêm solver không kiểm chứng
khả năng giải: EXE phải hỗ trợ một trong hai giao thức bên dưới.

## Bot HTTP (ví dụ bot_v11.exe)

Chọn mục **HTTP: <tên>**, điền Host/IP của server HAUI (hoặc server dùng cùng
API), Match ID đang hoạt động và Token trên GUI, rồi bấm **TỰ ĐỘNG CẢ TRẬN**.
GUI khởi tạo proxy chỉ lắng nghe tại `127.0.0.1` với cổng ngẫu nhiên và token
cục bộ ngẫu nhiên. Proxy kiểm tra config/status bằng GET trước khi chạy bot;
trận đã kết thúc, sai token hoặc lỗi kết nối sẽ chặn khởi chạy và ghi rõ lỗi.

Sau khi kiểm tra thành công, GUI gọi:

```text
bot.exe -transport http -url LOCAL_PROXY_URL -match MATCH_ID -token LOCAL_TOKEN
```

Proxy chuyển `/api/v1/matches/<id>/...` của bot sang
`/api/game/matches/<id>/...` của server:

- `setup` → `config` (GET).
- `assignment` → `agents` (POST).
- `state` và `result` → `status` (GET).
- `actions` → `answer` (POST).

Payload JSON được chuyển tiếp. Khi chưa có xe, state trả `day=-1`; khi trận
kết thúc, state trả HTTP 410. Nếu nộp vai trò nhận HTTP 400, proxy chỉ GET
status để kiểm tra: có xe rồi thì trả 409, không tự nộp lại. Proxy không tự
retry POST, không theo redirect và không tự quyết định vai trò/hành động.

Bot tự giải và quyết định lúc nộp. GUI không chạy luồng giải/nộp JSON song
song. Log `[Proxy]` hiển thị các bước API, chuyển ngày và lỗi ngay cả khi EXE
chưa xuất stdout. Token thật chỉ dùng ở kết nối proxy → server; CLI của bot
chỉ nhận token cục bộ. Cả hai token được che trong log chuyển tiếp.

TLS luôn xác minh chứng chỉ và hostname. Nếu cạnh EXE có `windows-roots.pem`,
GUI nạp thêm CA từ file đó (hữu ích với Python MSYS không có CA mặc định).
Chỉ dùng bundle CA tin cậy; giữ file này cạnh `bot_v11.exe`. Nếu không có,
dùng kho CA mặc định/`SSL_CERT_FILE` của Python. Không tắt xác minh TLS để
vượt lỗi. Chỉ chạy EXE tin cậy.

**DỪNG** hoặc đóng GUI sẽ dừng bot và proxy (trên Windows, dừng cả cây tiến trình).
Proxy cũng đóng khi bot thoát hoặc kiểm tra ban đầu thất bại. Request đã gửi
đến server trước khi dừng không thể thu hồi.
Bot thoát mã 0 chỉ có nghĩa tiến trình kết thúc bình thường, không xác nhận
trận đấu đã hoàn thành. Xem log bot/replay để biết kết quả trận đấu.

Bot HTTP chỉ dùng ở Live / TỰ ĐỘNG CẢ TRẬN; không tham gia Auto-Race, Arena
hoặc giải riêng một ngày. Bạn có thể tự cấu hình vai trò xe ở Mục 3 (hoặc bấm
Nộp Vai Trò Xe Ngay trước khi chạy), proxy sẽ áp dụng cấu hình đó khi bot vào
trận; nếu chọn "Tự động tối ưu bằng Solver", bot sẽ tự quyết định vai trò. Hạn
mức ms/ngày trên GUI không áp dụng cho bot này. Bot/server dùng API khác cần adapter riêng. Không chạy thêm
bot khác với cùng đội/token trong một trận đang được bot này điều khiển.

## Thay vị trí runner Procon26 mặc định

Đặt executable tại `solvers/runner.exe`, kèm DLL và tài nguyên mà solver cần,
rồi mở lại GUI. Thư mục làm việc của runner là thư mục chứa executable.
Không cần source C++ hoặc build lại GUI. Chỉ chạy executable từ nguồn tin cậy.

Trong danh sách solver, chọn **Runner EXE (Procon26 / solver thay thế)**.

GUI ưu tiên `solvers/runner.exe`, sau đó `bin/hexudon_runner.exe`, rồi
`build/hexudon_runner.exe`. Không còn dò repo `D:\Procon26` trong GUI.
Runner được chọn cũng thay vị trí Procon26 trong Auto-Race ALL và Arena;
đây là thay vị trí solver cũ, khác với nút **+ Thêm solver EXE** ở trên.
Các solver ACO/ALNS/... và bộ chấm điểm vẫn dùng `bin/hexudon.exe`
(hoặc `build/hexudon.exe`) với giao thức cũ. Không thay file này bằng runner.
Các script thi đấu riêng ngoài GUI chưa thay đổi.

## Giao thức Runner JSON

Mỗi yêu cầu khởi chạy một process mới, không có tham số dòng lệnh.
Process đọc một JSON UTF-8 từ stdin đến EOF và trả một JSON UTF-8 qua stdout.
Ghi log vào stderr, thoát với mã 0 khi thành công. Không giữ trạng thái giữa
hai lần gọi. GUI giới hạn thời gian và báo lỗi nếu phản hồi sai định dạng.

Chọn vai trò:

```json
{"op":"roles","config":{"agents":[0,1]}}
```

```json
{"ok":true,"roles":[1,0]}
```

Ví dụ config trên chỉ minh họa cấu trúc, không phải bản đồ hoàn chỉnh.
GUI gửi đầy đủ config bản đồ. `roles` có đúng một số nguyên 0 hoặc 1 cho mỗi
xe; ít nhất một xe tiếp xăng (1).

Lập kế hoạch nhận `{"op":"plan","config":{...},"state":{...},"stock":[...]}`.
`state` gồm `day`, `startsAt`, `endsAt`, `stepsCount`, `agents`, `others`,
`traffics`; các vai trò đã chọn nằm trong `state.agents[].kind`.
`stock` lấy từ stocks/stock của từng spot trong config.
Xem `build_procon26_payload` trong `gui.py` để biết chính xác phép chuyển đổi.

```json
{"ok":true,"plan":[[-20],[-20]]}
```

`plan` có đúng một mảng số nguyên cho mỗi xe, dùng mã hành động của game hiện
tại (ví dụ -20 là chờ 20 bước). Kiểm tra cấu trúc không thay thế kiểm tra
tính hợp lệ theo luật game. Khi thất bại, trả `{"ok":false,"error":"Lý do"}`.

Đổi thuật toán bên trong executable được tự do, nhưng phải giữ giao thức này.
Executable nhận tham số CLI hoặc định dạng khác cần được sửa/wrap phía solver.
Source, benchmark và build hiện có được giữ nguyên; chưa di chuyển hay xóa.
