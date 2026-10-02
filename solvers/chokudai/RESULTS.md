# Kết quả kiểm thử Chokudai repair solver

Ngày: 2026-09-29. Build Release, GCC 15.2.0, Boost 1.89, Windows UCRT64.
Đây là snapshot thử nghiệm đơn lẻ, chưa phải kết luận thống kê về độ mạnh.

## Kiểm thử chức năng

- C++ executable `chokudai_tests`: PASS.
- Phát lại 18 ngày trên 6 cấu hình, gồm có/không có xe refuel, fuel limit khác
  nhau, ao và đường, cập nhật vị trí/nhiên liệu/traffic giữa các ngày.
- 216 expansion và 105 lượt quét tầng; các hàng đợi Chokudai được mở rộng lại.
- 9/18 ngày tăng servings so với greedy seed khi tắt ALNS seed. Đây là bằng
  chứng Chokudai có thực hiện cải thiện, không chỉ trả lại seed.
- Mọi output có score trùng simulator, không giảm hai tiêu chí so với seed;
  giới hạn frontier được kiểm tra.
- Kiểm tra riêng guard khi tăng tiêu chí 1 nhưng giảm tiêu chí 2 và ngược lại,
  ưu tiên servings trước fuel, all-refuel, patrol hết nhiên liệu, ngân sách >50s.
- Python `test_protocol.py`: **14 passed**. Gồm giao thức native/GUI,
  history, role selection, ngày/vai trò/tham số sai, deadline đã hết, ngân sách
  1ms, map không có spot và tính lặp lại khi cố định số expansion.

## Benchmark với ALNS

Mỗi cặp dùng cùng cấu hình và vai trò đã chọn một lần. ALNS đối chứng chạy
`plan_day("alns")` với ngân sách đầy đủ; solver mới dành 30% thời gian cho seed
(tối đa 12s), rồi chạy Chokudai. Hai solver có quỹ đạo trạng thái riêng qua các
ngày. Mô phỏng chỉ tính traffic của đội mình, không tái hiện đối thủ online.

| Case | Ngân sách/ngày | Số ngày | ALNS: tiêu chí 1 / 2 / udon | Solver mới | Chênh udon |
|---|---:|---:|---|---|---:|
| Q01 | 3s | 3 ngày đầu | 4 / 12 / 51 | 4 / 12 / 50 | -1 |
| Q06 | 50s | Ngày đầu | 13 / 13 / 37 | 13 / 13 / 36 | -1 |
| Q03 | 3s | Toàn trận 4 ngày | 10 / 40 / 134 | 10 / 40 / 136 | +2 |

Trong cả ba lượt, solver mới không giảm loại toàn trận hay loại của bất kỳ
ngày đã kiểm tra nào so với ALNS. Ở Q03 và Q01, mọi ngày đã kiểm tra thu đủ
số loại thể hiện trong bảng; bảng Q06 chỉ báo điểm thực đo, không khẳng định
13 là số loại tối đa khả thi của map.

Lượt 50s: solver mới kết thúc sau **49.750ms**, thực hiện 19.588 expansion,
3.713 lượt quét và 706.040 lần đánh giá decode. ALNS đối chứng mất 50.002ms.
Các lượt 3s của solver mới mất khoảng 2.850–2.851ms, có chừa thời gian trả JSON.

**Phân biệt nguyên nhân:** trong ba benchmark map thật này, điểm cuối từng ngày
của solver mới bằng điểm seed trước Chokudai. Vì vậy, lợi thế +2 trên Q03 có
thể đến từ cấu hình seed, tie-break và quỹ đạo trận; không được quy riêng cho
Chokudai. Chỉ bộ fixture nhỏ hiện thể hiện mức tăng trực tiếp sau Chokudai.

## Giới hạn và bước tiếp theo

- Chưa chứng minh solver mới mạnh hơn ALNS; hai lượt thua 1 udon cho thấy còn
  cần điều chỉnh phân bổ seed/search và lựa chọn repair.
- Guard bảo vệ hai tiêu chí của ngày hiện tại so với incumbent cùng trạng thái,
  không phải bảo đảm đủ loại toàn bộ tương lai dưới mọi đối thủ.
- Travel choices được thử lại theo decoder, chưa lưu đầy đủ lịch rendezvous
  như một thành phần của node. Đây là điểm đáng thử tiếp nếu seed đã mạnh nhưng
  nhiều trăm nghìn decode không tạo thêm udon.
- Deadline trong thư viện là hợp tác; cần timeout process từ caller trên map
  lớn bất thường. Chưa đo peak RAM của process; chỉ kiểm tra giới hạn số node.
- Benchmark tiếp nên chạy nhiều seed, nhiều cấu hình vai trò, và so sánh cả
  ALNS-only, greedy+Chokudai, ALNS+Chokudai dưới cùng ngân sách.

Raw JSON của các lượt đo được lưu tại:

- `build/chokudai/benchmark-q01-3s.json`
- `build/chokudai/benchmark-q06-50s.json`
- `build/chokudai/benchmark-q03-full-3s.json`

Thư mục build bị Git ignore; các lệnh tái tạo nằm trong `README.md` cùng thư mục
solver. Chất lượng timed search có thể khác giữa các lần chạy và phần cứng.
