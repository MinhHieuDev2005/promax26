# Danh sách kiểm tra cuối cùng trước thi đấu

Ngày: 2026-10-15. Chỉ xác minh vận hành cục bộ; không truy cập máy chủ chính thức.
Xem kết quả chạy cuối và bằng chứng gốc tại `results/final-operations/REPORT.md`.

## 1. Nhận diện ứng dụng

| Phiên bản | Tệp mở GUI trên Windows | GUI cục bộ | Ứng dụng WSL | Tệp dừng |
| --- | --- | --- | --- | --- |
| H2, ứng viên chính | Open-HexaUdon-H2.cmd | http://127.0.0.1:8766 | /home/hexa/release/hexa_udon_H2 | Stop-HexaUdon-H2.cmd |
| B, dự phòng | Open-HexaUdon-B.cmd | http://127.0.0.1:8767 | /home/hexa/release/hexa_udon_B | Stop-HexaUdon-B.cmd |
| Production gốc | Open-HexaUdon.cmd | http://127.0.0.1:8765 | /home/hexa/build-release/hexa_udon | Stop-HexaUdon.cmd |

`solver_H2` và `solver_B` là chương trình benchmark, KHÔNG phải client thi đấu.
Các thay đổi này không thay thế hoặc biên dịch lại tệp thực thi production.

SHA256 dự kiến:

```text
H2          6ac30c33292aa33234c84bea757376b7b30f8cf05432d8b91e3f332464331c04
B           feaa67c74d8b3f21ebf3ee2797d4de765924cbeb97b8d2d1bf496aed727399d1
Production  d864d3fd2f325773cbcd594dc93063b63882ca07fa5947365944fa0e8ec7b903
```

## 2. Mở H2 trên Windows

Chạy `D:\30013-o-udon\Open-HexaUdon-H2.cmd`. Tệp này khởi động dịch vụ systemd
`hexa-udon-gui-h2.service` trong WSL HexaUdon và mở trình duyệt. Giữ cửa sổ khởi chạy
mở hoặc thu nhỏ. Chỉ phản hồi HTTP thành công chưa đủ xác định binary:
nếu chưa chắc chắn, kiểm tra lệnh của dịch vụ:

```powershell
wsl -d HexaUdon -u root --exec systemctl show hexa-udon-gui-h2.service -p ExecStart -p ActiveState
```

H2 phải hiển thị `gui.py --binary /home/hexa/release/hexa_udon_H2 --port 8766`.
B dùng dịch vụ riêng `hexa-udon-gui-b.service` và port 8767, không dùng 8765 của production.

## 3. CHỈ bắt đầu trận khi được phép

- Xác nhận URL máy chủ, token, protocol và đúng trận đấu với ban tổ chức.
- Chọn `Procon` cho protocol `/setting`. Mock đã kiểm thử là Procon, KHÔNG phải HAUI.
- Với HAUI, chọn backend đó và đúng trận; khả năng tương thích HAUI thực tế
  vẫn CHƯA ĐƯỢC XÁC MINH (NOT VERIFIED) bởi bộ kiểm thử mock này.
- Nhập base URL và token được cho phép. Không công khai token qua ảnh chụp màn hình.
- Kiểm tra kết nối, rồi chạy thử không gửi quyết định (dry-run) nếu được phép.
  Chỉ chọn Execute / chạy thật và xác nhận sau khi chắc chắn không có bot khác điều khiển trận.
- Giữ máy không ngủ, WSL hoạt động và mạng ổn định. Không chỉnh giờ Windows/WSL
  trong trận. Không giảm khoảng dự phòng an toàn mặc định 3 giây của GUI.
- Hai GUI là các tiến trình độc lập, KHÔNG có khóa trận đấu giữa các tiến trình.
  Không chạy B và H2 đồng thời trong cùng trận thật.

## 4. Dừng và khôi phục

Dùng nút Stop của GUI để dừng client, hoặc tệp Stop tương ứng để dừng dịch vụ GUI
và các tiến trình con. Các tệp Stop yêu cầu xác nhận. Chúng KHÔNG chấm dứt WSL,
không dừng dịch vụ GUI khác và giữ lại phiên đã lưu.
Đóng cửa sổ khởi chạy hoặc trình duyệt không phải thao tác Stop được hướng dẫn.

Ghi lại thư mục phiên hiển thị trong trạng thái GUI trước khi dừng. Dữ liệu vận hành
nằm tại `/home/hexa/.hexa-udon-gui/execute-*/session` (riêng cho mỗi lần chạy).
Bấm Execute lại tạo phiên MỚI, KHÔNG phải khôi phục.

Nếu HTTP POST đang chờ xử lý lúc bị ngắt, kết quả có thể chưa xác định. Kiểm tra
day/revision trên máy chủ trước; không gửi lại quyết định chưa rõ kết quả một cách mù quáng.
Kiểu khôi phục đã kiểm thử là dừng có kiểm soát với phiên đã lưu, không phải sau crash
hoặc mất phản hồi xác nhận ACK.

Khôi phục bằng CLI trong WSL sau khi đặt `PROCON_TOKEN` an toàn và thay các giá trị
URL, SESSION bằng ĐÚNG trận đấu và phiên đã lưu:

```sh
/home/hexa/release/hexa_udon_H2 show-state --session-dir SESSION
/home/hexa/release/hexa_udon_H2 recover --base-url URL --token-env PROCON_TOKEN --session-dir SESSION --log-dir SESSION/recovery-log
```

Khôi phục mặc định dùng dry-run. Chỉ thêm `--execute` sau khi được phép và đã làm rõ
kết quả các POST chưa xác định. GUI không có nút khôi phục riêng.

## 5. Chuyển sang B an toàn

Dừng H2 và xác nhận client đã thoát. Kiểm tra trạng thái đã lưu và day/revision hiện tại
trên máy chủ. Mở `Open-HexaUdon-B.cmd`. Không bấm Execute với phiên mới vào cùng trận
rồi mặc định trạng thái được tiếp nối. Trước tiên dùng `show-state` và `recover` ở chế độ
dry-run của B trên phiên đã lưu; khôi phục chéo binary vẫn CHƯA ĐƯỢC XÁC MINH (NOT VERIFIED).
Nếu chưa chắc chắn, hỏi ban tổ chức thay vì gửi lại hành động. Phạm vi xác minh cục bộ
được hỗ trợ là B chạy trọn trận độc lập và khôi phục sau dừng có kiểm soát bằng cùng binary.

## 6. Xác minh quyết định được chấp nhận trước deadline

Đối chiếu thời điểm máy chủ nhận và xác thực request với deadline của ngày đó, kết hợp
phản hồi chấp nhận `valid`, revision và bản ghi gửi quyết định đã lưu của client.
Chỉ thời điểm ACK không chứng minh được thời điểm nhận request. Phản hồi 403 sau khi
hết thời gian đăng ký hoặc hết ngày có thể là từ chối đúng quy định, không phải lỗi solver.

Trace mock lưu `receipt_ns`, `validation_ns`, `response_ns`,
`receipt_monotonic_ns`, `elapsed_ms` đo bằng đồng hồ đơn điệu, day, revision và deadline.
Các trường `startedAtMs`/`finishedAtMs` do C++ lưu dùng đồng hồ thời gian thực (wall clock),
không phải đồng hồ đơn điệu. Log POST cũ sau cập nhật có thể ghi thời lượng bằng 0;
không dùng giá trị đó làm bằng chứng RTT. Bất liên tục giữa wall clock và đồng hồ đơn điệu
khiến kiểm tra thời lượng thất bại dù request đã được chấp nhận. Cần log máy chủ của ban tổ chức
để xác nhận có thẩm quyền thời điểm máy chủ từ xa nhận request.

## 7. Kiểm toán đồng hồ và giới hạn còn lại

Các lượt chạy cuối mới nhất: trọn trận qua launcher B/H2 và trận 60 giây/ngày đều PASS;
delay 0/20/50/100/1500ms PASS. Khôi phục B sau dừng có kiểm soát PASS. Khôi phục H2 hoàn thành
và trạng thái khớp, nhưng kiểm tra timing nghiêm ngặt FAIL vì một RTT wall-clock của client
là -223ms. Không coi hoàn thành trận thành công là timing đã được xác minh. Nguyên nhân
chính xác của điều chỉnh đồng hồ vẫn chưa rõ; xem báo cáo cuối.

Trace cũ với delay 1500ms ở ngày 2 revision 2 đo được 1500.715443ms bằng đồng hồ đơn điệu
nhưng chỉ 982.546391ms bằng wall clock: chênh lệch -518.169052ms ngay trong CÙNG request
phía máy chủ. Request được nhận trước deadline công bố 4029.830ms; xác thực trước deadline
3047.538ms. Mọi POST được chấp nhận trong trace đều được nhận trước deadline
(khoảng dư nhỏ nhất 1688.497ms). Đây không phải bằng chứng nộp muộn.

`SessionController::deadline` chuyển thời gian tuyệt đối của máy chủ tính bằng giây epoch
thành thời gian còn lại theo wall clock, trừ dự phòng an toàn rồi neo một lần vào `steady_clock`.
Timer và thời gian planner đã sử dụng được đo bằng `steady_clock`; thao tác chờ dùng cùng đồng hồ.
Bước nhảy wall clock sau đó không đặt lại deadline steady đã có. Cách này tránh bước nhảy của
đồng hồ đo thời lượng nhưng không xử lý sai lệch ban đầu giữa client/máy chủ, chỉnh đồng hồ
sau chuyển đổi, máy ảo tạm dừng hoặc độ trễ mạng từ xa chưa biết. Chưa chứng minh được lỗi
thuật toán; binary và logic solver được giữ nguyên.

CHƯA ĐƯỢC XÁC MINH (NOT VERIFIED): nguyên nhân chính xác của bước nhảy đồng hồ cũ
(đồng bộ WSL là giả thuyết, không phải kết luận); đồng bộ đồng hồ với máy chủ từ xa;
hành vi khi máy ảo tạm dừng/chỉnh giờ tùy ý; độ trễ chính xác từng pha client nhận
GET/parse/waypoint/serialize; chính sách lỗi chính thức; phân xử tương tác đối thủ;
tương thích HAUI/máy chủ thi đấu thật; khôi phục mất ACK/crash; khôi phục chéo binary;
hiển thị và thao tác bấm nút trực tiếp trên trình duyệt. Cả 5%, 50ms lẫn dự phòng hiện tại
đều không phải bảo đảm tuyệt đối.

## 8. Kiểm tra máy chủ chính thức sau khi được phép

Chỉ thực hiện sau khi được phép rõ ràng: xác minh protocol/phiên bản và chính sách lỗi;
xác minh giờ máy chủ và cách áp dụng deadline; đo phần đuôi phân bố RTT và sai lệch đồng hồ
trong điều kiện đại diện; trước tiên kiểm tra xác thực bằng request chỉ đọc; xác minh đăng ký xe,
revision được chấp nhận và log thời điểm nhận request trong trận tập được ban tổ chức cho phép;
thử khôi phục phiên đã lưu tại đó. Chỉ chạy MỘT client cho trận đó.
Tăng dự phòng vận hành nếu RTT/sai lệch đo được yêu cầu; không chỉnh thuật toán solver để che
timeout truyền tải. Giữ sẵn B và các checksum gốc.

Việc thực hiện danh sách này không bao gồm kết nối máy chủ thật, triển khai, ghi đè production,
commit hoặc push.
