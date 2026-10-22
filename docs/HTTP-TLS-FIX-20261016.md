# Bản sửa HTTP/TLS ngày 16/10/2026

## Phạm vi

Sửa tầng HTTP dùng chung, không sửa thuật toán production/B/H2. Không thay binary cũ,
không đổi launcher, không truy cập server thật, không commit/push.
Đây là sửa lỗi phân loại đã tái hiện được, không phải khẳng định timeout TLS là nguyên nhân
chắc chắn của mọi sự cố cũ: log cũ đã mất chi tiết lỗi truyền tải.

## Thay đổi

- Theo dõi sự kiện bắt đầu xuất header/data HTTP qua callback libcurl. Không lưu nội dung
  header/body và không in debug chứa token. Dữ liệu bắt tay TLS không được coi là HTTP POST.
- Timeout trước sự kiện gửi HTTP được phân loại ConnectionTimeout: vòng retry đầu ngày
  hiện có được phép thử lại, vẫn chịu backoff và deadline. Không có vòng retry vô hạn mới.
- Timeout sau khi bắt đầu gửi HTTP vẫn là TransferTimeout, kết quả POST chưa xác định.
  Không tự gửi lại; nếu chưa có quyết định được xác nhận cho ngày đó thì vẫn RecoveryRequired.
- Proxy CONNECT cũng được coi là đã bắt đầu gửi một cách bảo thủ; không suy diễn rằng
  chắc chắn chưa gửi chỉ dựa vào số byte body. Các lỗi TLS không phải timeout không tự retry mới.
- Giữ mã curl, thời lượng monotonic và requestStarted trong thông báo lỗi. API che token
  rồi ghi bản ghi http-transport riêng, không bị cập nhật session ghi đè mất chẩn đoán.
- requestStartedAt nay được lấy trước transport thay vì sau khi hoàn thành.

Phạm vi tự retry được kiểm tra ở đây là POST đầu ngày. Đăng ký xe không được thêm vòng
retry mới. Không bỏ cơ chế dừng an toàn đối với POST thực sự chưa rõ kết quả.

## Kiểm thử

- PASS: mock TLS không hoàn thành bắt tay -> ConnectionTimeout, requestStarted=false.
- PASS: mock HTTP nhận đủ POST nhưng giữ lại ACK -> TransferTimeout, requestStarted=true.
- PASS: session thử lại được sau ConnectionTimeout; POST thành công cập nhật accepted_days.
- PASS: session gặp TransferTimeout chuyển RecoveryRequired và chặn lần gửi tiếp theo.
- PASS: chẩn đoán API giữ mã lỗi và che token cả dạng thô lẫn URL-encoded.
- PASS: 5/5 CTest ở Debug, bật assert; kiểm tra GUI hiện có cũng PASS.
- PASS: binary Release production sửa HTTP chạy trận mock 4 ngày, 12 giây/ngày, điểm [8,18,20].
- PASS: binary Release H2 sửa HTTP chạy cùng cấu hình mock, điểm [9,16,16].
  Các trận này xác minh HTTP/state/deadline bình thường; không phải thử nghiệm 5–6 đội
  hoặc trận HTTPS đầy đủ có chèn lỗi TLS. Kiểm thử TLS dùng transport thực trên loopback;
  retry và chặn gửi trùng được kiểm tra thêm ở tầng session/API.

Bằng chứng: `results/http-fix-20261016/` chứa matches.json, log HTTP/session từng trận,
unit-tests.log, transport-tests.log, gui-tests.log, http-fix.patch và manifest.json.
SHA256 production gốc, H2 cũ và B cũ giữ nguyên.

## Binary mới, chưa triển khai

- `/home/hexa/release/http-fix-20261016/hexa_udon_H2_httpfix`
- `/home/hexa/release/http-fix-20261016/hexa_udon_production_httpfix`

Cả hai build Release với GCC 13.3.0. SHA256, Git revision và đường dẫn snapshot nguồn
nằm trong `results/http-fix-20261016/manifest.json`; cờ biên dịch HTTP nằm trong các tệp
*-http-flags.make. Source H2 chỉ thay hai tệp protocol; thuật toán trong snapshot giữ nguyên.

**GUI tại 8765/8766 vẫn dùng binary cũ.** Chưa tự đổi sang bản sửa khi chưa được phép.
Có thể mở GUI thử riêng cho H2 bằng PowerShell, không thay dịch vụ đang chạy:

```powershell
wsl -d HexaUdon -u hexa --cd /mnt/d/30013-o-udon --exec python3 -B gui.py --binary /home/hexa/release/http-fix-20261016/hexa_udon_H2_httpfix --port 8768
```

Mở http://127.0.0.1:8768/ trong trình duyệt. Lệnh trên chỉ mở GUI, không tự kết nối
server thi đấu. Chỉ nhập URL/token và chạy thật sau khi được phép. Không để hai client
điều khiển cùng một đội trong cùng trận. Dùng Stop trong GUI trước khi đóng tiến trình.

## Giới hạn

Không bảo đảm chữa được mất ACK thật, mạng/server quá tải, hoặc clock WSL nhảy lùi.
Không thay đổi đồng hồ hay dịch vụ đồng bộ giờ. Chưa xác minh trận thật, nhiều đội,
proxy phức tạp, hoặc tự khôi phục sau mất ACK. Không tăng timeout để che lỗi và không
bỏ dừng an toàn. Cần dùng chẩn đoán mới nếu sự cố thực tế tái diễn.
