# Chokudai H24 — throughput role selector

H24 là solver mới độc lập; không thay đổi GUI hoặc executable cũ. Search plan dùng
production ALNS, còn `op=roles` bắt đầu từ selector ALNS rồi giữ tối đa một xe tiếp xăng.
Mục đích là tránh mất thông lượng khi selector cũ chọn nhiều xe tiếp xăng trên đội
xe lớn. Đây là heuristic tổng quát, không chứa tọa độ, route hoặc score của test.

Case kiểm soát: `cases/user-input-24x24.json`. Snapshot ngày 0:
`solver_learning/snapshots/user-24x24-d0.json`.

## Kết quả đã replay

Ngân sách 3000ms/ngày, seed 1, vai trò `[0,0,1,0,0]`:

```text
C1: 10/10
C2: 70/70
C3: 213
Daily servings: 21, 28, 31, 31, 34, 34, 34
```

Checkpoint: `solver_learning/runs/u24-h24b-h24-3000-1.json`.
Evaluator: `bin/hexudon.exe trace` không thay đổi.

Thêm `build/chokudai_h24/chokudai_h24_runner.exe` vào GUI bằng chức năng
**+ Thêm solver EXE**. GUI không cần sửa phần chọn xe; chính `op=roles` của H24
trả vai trò `[0,0,1,0,0]` cho case này.

Đây là selector nhanh tương thích timeout GUI. Muốn dùng kết quả tối ưu sâu,
chạy `chokudai_h24_role_optimizer.exe` trước trận và đặt mask thắng bằng chế độ
chọn xe thủ công; optimizer không được nhét vào callback GUI vì phép xác nhận
toàn trận có thể mất khoảng 60–150 giây.

## Role optimizer cho 16×16, 24×24 và 32×32

Executable độc lập:

```powershell
$env:HEXUDON_THREADS=4
build/chokudai_h24/chokudai_h24_role_optimizer.exe `
  cases/user-input-24x24.json 1000 `
  solver_learning/role-result.json 1 profile
```

`profile` dùng hai tầng:

1. Sàng lọc song song toàn trận. `16×16` xét tối đa 1 xe tiếp xăng,
   `24×24` tối đa 2, `32×32` tối đa 3.
2. Giữ mọi mask có đúng một xe tiếp xăng và hai mask tốt nhất của mỗi nhóm
   còn lại, rồi đánh giá tuần tự với cùng seed/ngân sách. Chỉ nghiệm đạt đủ
   toàn bộ thương hiệu ở mọi ngày mới được ưu tiên; sau đó mới tối đa Udon.

Không chọn chỉ theo kích thước: toàn bộ map, số xe, số ngày, vị trí quán,
stock, fuel và vị trí xuất phát đều được mô phỏng. Không có index xe cố định.

Trên case `24×24`, profile 1s chọn `[0,0,0,1,0]`; checkpoint độc lập 3s
replay `10/70/212`. Một lượt xác nhận tuần tự sâu đạt `10/70/214`. Dao động
là do ALNS time-based; nên chạy seed 1–3 và chọn theo feasibility trước,
median Udon sau nếu thời gian chuẩn bị cho phép.

Profile `16×16` đã được triển khai nhưng chưa thể tuyên bố score thực nghiệm
cho đến khi cấu hình đang nằm trong nội dung chat được cung cấp thành file JSON.

## Kết quả profile bổ sung

Các input authoritative mới:

| Bảng | Xe | Ngày | Vai trò thắng | Replay 3s/ngày |
|---|---:|---:|---|---:|
| 16×16 | 4 | 6 | `[0,1,0,0]` | `8/48/94` |
| 24×24-B | 7 | 5 | `[0,0,0,0,1,0,0]` | `14/70/260` |
| 32×32 | 7 | 5 | `[1,1,0,0,0,0,0]` | `14/70/265` |

Điều này bác bỏ quy tắc cố định “mọi map chỉ dùng một xe tiếp xăng”. Profile
24×24-B cần một xe tiếp xăng, trong khi profile 32×32 này chọn hai. Cả hai
checkpoint đều được replay bằng core evaluator không thay đổi và đạt 14 loại
trong cả năm ngày.

Checkpoint:

- `solver_learning/runs/u24b-roleopt-final-h24-3000-1.json`
- `solver_learning/runs/u32-roleopt-final-h24-3000-1.json`
- `solver_learning/runs/u16-roleopt-final-h24-3000-1.json`
