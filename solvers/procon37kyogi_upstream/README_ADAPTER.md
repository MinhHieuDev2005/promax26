# Procon37 Kyogi adapter

Nguồn: <https://github.com/yss19411208/procon37kyogi>, commit
`808367d559c40b6061434e37bc33ffb8d756dc15`, giấy phép MIT.

GUI gọi `../procon37kyogi_runner.py` bằng giao thức Runner JSON. Adapter dùng:

- ensemble model và mô phỏng riêng trên map để chọn số/vị trí xe tiếp nhiên liệu;
- greedy, learned policy và planned-route policy để tạo nhiều điểm xuất phát;
- multi-start LNS phá/sửa/chuyển đoạn đường đến khi hết `timeLimitMs`;
- simulator gốc kiểm tra ứng viên và giữ nghiệm tốt nhất theo khóa điểm.

Chọn **Hybrid Japan LNS (Procon37 + SA/LNS)** trong danh sách Solver Thuật toán.
Không cần cài dependency ngoài Python 3.10+.
