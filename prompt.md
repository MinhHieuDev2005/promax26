# NHIỆM VỤ: NÂNG CẤP SOLVER HEXUDON — PROCON

Repository hiện tại chứa nhiều solver/thuật toán đã được phát triển cho bài **Hexudon**.

Hãy đọc, phân tích, benchmark toàn bộ các solver hiện có và tạo một **solver mới mạnh hơn**, tận dụng:

- Chokudai Search
- các heuristic tốt nhất từ solver hiện tại
- Beam Search / Greedy / Local Search nếu đang tồn tại và có ích
- các kỹ thuật search khác đã được triển khai trong repository

## MỤC TIÊU

Test JSON hiện tại có một solver đạt khoảng:

```text
Criterion 3 / Udon count = 223
```

Mục tiêu mong muốn:

```text
Criterion 1: PHẢI ĐẠT
Criterion 2: PHẢI ĐẠT
Criterion 3: hướng tới >= 230 Udon
```

## THỨ TỰ ƯU TIÊN TUYỆT ĐỐI

Optimization objective phải được hiểu theo thứ tự:

```text
PRIORITY 1: Thỏa mãn Criterion 1
      ↓
PRIORITY 2: Thỏa mãn Criterion 2
      ↓
PRIORITY 3: Tối đa hóa số lượng Udon
```

Criterion 1 và Criterion 2 là **HARD CONSTRAINT**.

Không được chấp nhận solution kiểu:

```text
Criterion 1 = fail
Criterion 2 = pass
Udon = 240
```

hoặc:

```text
Criterion 1 = pass
Criterion 2 = fail
Udon = 250
```

Dù Criterion 3 cao hơn.

Solution chỉ được xem là candidate hợp lệ khi:

```text
criterion_1_satisfied == true
AND
criterion_2_satisfied == true
```

Sau đó mới so sánh theo Criterion 3.

---

# 1. ĐỌC LUẬT VÀ XÁC ĐỊNH CHÍNH XÁC 3 TIÊU CHÍ

Trước khi sửa thuật toán, hãy tìm trong repository, tài liệu, evaluator, validator, score calculator hoặc code liên quan để xác định chính xác:

```text
Criterion 1 là gì?
Criterion 2 là gì?
Criterion 3 được tính như thế nào?
```

Không được đoán.

Tìm các phần như:

```text
score
judge
evaluate
validator
validation
criterion
objective
udon
hex
board
solution
```

Nếu repository có official judge/evaluator thì evaluator đó là nguồn authoritative.

Hãy viết lại thành:

```text
Criterion 1:
- điều kiện:
- cách tính:
- điều kiện fail:

Criterion 2:
- điều kiện:
- cách tính:
- điều kiện fail:

Criterion 3:
- cách đếm Udon:
- yếu tố ảnh hưởng:
```

Đặc biệt xác định:

```text
Criterion 1/2 có phải binary constraint không?
hay có score riêng?

Có threshold tối thiểu không?

Có trường hợp Criterion 3 tăng nhưng Criterion 1/2 giảm không?
```

---

# 2. NGUYÊN TẮC SO SÁNH SOLUTION

Tạo một comparator duy nhất cho toàn bộ solver.

Ví dụ conceptual:

```python
def better(a, b):

    if a.criterion1_valid != b.criterion1_valid:
        return a.criterion1_valid

    if a.criterion2_valid != b.criterion2_valid:
        return a.criterion2_valid

    return a.udon_count > b.udon_count
```

Tuy nhiên phải điều chỉnh comparator dựa trên luật thật.

Nếu Criterion 1 hoặc 2 có giá trị score chứ không phải boolean thì phải sử dụng logic tương ứng.

Điểm quan trọng:

```text
KHÔNG cộng các tiêu chí bằng weighted sum tùy tiện.
```

Ví dụ KHÔNG dùng:

```text
score =
1000 * criterion1
+ 100 * criterion2
+ udon
```

nếu điều đó cho phép criterion bắt buộc bị trade-off.

Ưu tiên sử dụng **lexicographic objective**:

```text
Criterion 1
→ Criterion 2
→ Criterion 3
```

hoặc hard feasibility check theo đúng luật.

---

# 3. AUDIT TOÀN BỘ SOLVER HIỆN TẠI

Tìm tất cả file liên quan:

```text
solver*
search*
beam*
chokudai*
greedy*
dfs*
local*
anneal*
heuristic*
state*
score*
evaluate*
```

Không giả định tên file.

Với từng solver, phân tích:

```text
Algorithm
State representation
Move generation
Evaluation
Pruning
Move ordering
Search depth
Beam width
Randomization
Local optimization
Runtime
```

Sau đó đặc biệt đánh giá:

```text
Solver có bảo đảm Criterion 1 không?
Solver có bảo đảm Criterion 2 không?
Solver tối ưu Criterion 3 như thế nào?
```

---

# 4. BENCHMARK BASELINE

Chạy tất cả solver trên cùng file JSON test.

Tạo bảng:

| Solver | C1 | C2 | Udon | Valid | Runtime | Algorithm |
|---|---:|---:|---:|---|---:|---|
| solver_A | PASS | PASS | 223 | YES | ... | ... |
| solver_B | ... | ... | ... | ... | ... | ... |

Phải xác định chính xác solver hiện tại đạt:

```text
223 Udon
```

và xác nhận đồng thời:

```text
Criterion 1 = PASS
Criterion 2 = PASS
```

Solution này trở thành:

```text
BASELINE
```

Không được bắt đầu optimization trước khi tái hiện được baseline.

---

# 5. BEST-SOLUTION ACCEPTANCE

Một solution mới chỉ được phép thay thế best solution nếu:

```text
Criterion 1 đạt
AND
Criterion 2 đạt
AND
Criterion 3 tốt hơn best hợp lệ hiện tại
```

Pseudo:

```python
if not satisfy_criterion_1(candidate):
    reject(candidate)

elif not satisfy_criterion_2(candidate):
    reject(candidate)

elif candidate.udon > best.udon:
    best = candidate
```

Các state chưa đạt C1/C2 có thể được giữ trong search **chỉ khi luật cho phép chúng là trạng thái trung gian có khả năng trở thành solution hợp lệ sau này**.

Nhưng final output tuyệt đối phải thỏa C1/C2.

---

# 6. PHÂN TÍCH SOLUTION 223

Không chỉ chạy search rộng hơn.

Phải phân tích tại sao baseline dừng ở:

```text
223
```

Tìm:

```text
dead regions
blocked Udon positions
early irreversible decisions
conflicting placements
fragmented free space
poor move ordering
greedy traps
beam collapse
insufficient lookahead
```

Đồng thời kiểm tra những move tạo Udon nhiều hơn có làm:

```text
Criterion 1 fail
hoặc
Criterion 2 fail
```

hay không.

Đây là điểm rất quan trọng.

Có thể 223 không phải do search yếu đơn thuần, mà vì nhiều candidate >223 phá Criterion 1/2.

Phải phân biệt hai nguyên nhân.

---

# 7. CHOKUDAI SEARCH

Sử dụng Chokudai Search làm một trong các engine chính.

Không implement chỉ để có tên thuật toán.

Thiết kế các queue theo depth:

```text
beam[0]
beam[1]
beam[2]
...
beam[max_depth]
```

Search conceptual:

```text
while within time budget:

    for depth in range(max_depth):

        take promising states from beam[depth]

        generate legal moves

        prune impossible states

        evaluate remaining states

        push into beam[depth + 1]
```

Điểm khác biệt so với Beam Search thông thường:

```text
không loại bỏ toàn bộ các state chưa được mở rộng sau mỗi layer
```

Cho phép các candidate tốt ở nhiều vùng search tiếp tục tồn tại qua nhiều iteration.

---

# 8. FEASIBILITY-FIRST CHOKUDAI SEARCH

Chokudai Search phải nhận thức Criterion 1 và 2.

State nên có metadata tối thiểu:

```text
criterion1_status
criterion2_status

criterion1_remaining_requirement
criterion2_remaining_requirement

current_udon

future_udon_potential

legal_moves
```

Nếu Criterion 1/2 có thể kiểm tra incremental, hãy update chúng ngay khi apply move.

Không tính lại toàn bộ board nếu không cần.

---

# 9. PRUNING THEO CRITERION 1 VÀ 2

Đây là phần cực kỳ quan trọng.

Nếu một state đã đi đến tình trạng mà về mặt toán học:

```text
không còn khả năng đạt Criterion 1
```

hoặc:

```text
không còn khả năng đạt Criterion 2
```

thì prune ngay.

Ví dụ conceptual:

```python
if max_possible_c1(state) < required_c1:
    prune

if max_possible_c2(state) < required_c2:
    prune
```

Việc này giúp dành search budget cho những state có khả năng tạo final solution hợp lệ.

---

# 10. EVALUATION FUNCTION

Không dùng:

```text
eval = current_udon
```

làm evaluator duy nhất.

Evaluator nên phản ánh:

```text
khả năng đạt Criterion 1
khả năng đạt Criterion 2
current Udon
future Udon potential
mobility
flexibility
space fragmentation
blocking cost
```

Nhưng Criterion 1/2 vẫn không được biến thành soft objective nếu chúng là hard constraint.

Có thể thiết kế conceptual:

```text
Tier A:
states vẫn có khả năng hoàn thành C1/C2

Tier B:
trong các state Tier A:
    current_udon
    future_udon_potential
    flexibility
```

---

# 11. CHOKUDAI + GREEDY

Thử:

```text
Strong Greedy Construction
        ↓
Valid solution satisfying C1 + C2
        ↓
Chokudai Search
        ↓
Improve Udon
```

Greedy hiện tại nếu đã tạo được 223 hợp lệ có thể là seed cực tốt.

Không bắt buộc Chokudai phải search từ empty board.

Có thể search quanh vùng:

```text
220–223 Udon
```

để tập trung tìm improvement.

---

# 12. DESTROY & REPAIR

Đây là hướng cần ưu tiên vì baseline đã ở 223 và target chỉ cách 7 Udon.

Thử:

```text
223 valid solution
        ↓
remove một vùng nhỏ
        ↓
reconstruct region bằng Chokudai
        ↓
check C1
        ↓
check C2
        ↓
compare Udon
```

Neighborhood:

```text
remove 1 placement
remove 2 placements
remove 3 placements
```

hoặc spatial:

```text
remove placements trong một connected region
```

Sau đó search lại vùng đó.

Mục tiêu:

```text
223
→ 224
→ 225
→ ...
→ 230
```

Không nhất thiết phải tìm 230 trong một bước.

---

# 13. LOCAL SEARCH

Sau mỗi solution hợp lệ tốt hơn:

```text
local_search(solution)
```

Thử các move dạng:

```text
remove 1 → add 2
remove 2 → add 3
remove 3 → rebuild region
swap placements
reorder placements
```

Nhưng sau mỗi mutation phải verify Criterion 1 và 2.

---

# 14. LOOKAHEAD

Thêm shallow lookahead khi xếp hạng move.

Ví dụ:

```text
move A:
+1 Udon ngay
future +0

move B:
+0 Udon ngay
future +3
```

Không được chỉ ưu tiên A.

Thử:

```text
1-step lookahead
2-step lookahead
greedy rollout
```

Đặc biệt tại các state gần:

```text
220+
```

---

# 15. MOVE ORDERING

Candidate order nên xét:

```text
impact on Criterion 1
impact on Criterion 2

immediate Udon
future Udon

blocking cost
scarcity
constraint
flexibility
```

Ưu tiên những move:

```text
giữ C1/C2 an toàn
+
tăng Udon
+
ít phá future search space
```

---

# 16. DIVERSITY

Không để Chokudai/Beam chứa hàng trăm state gần giống nhau.

Sử dụng:

```text
board hash
placement hash
region signature
structural signature
```

Giới hạn:

```text
top K states / bucket
```

để duy trì nhiều chiến lược search.

---

# 17. TRANSPOSITION TABLE

Nếu hai chuỗi move dẫn đến cùng state:

```text
A → B
```

và:

```text
B → A
```

không search lặp lại.

Dùng:

```text
state_hash
Zobrist hash
compact board representation
```

và lưu:

```text
visited[state_hash]
```

Nếu gặp lại state với quality không tốt hơn thì prune.

---

# 18. MULTI-START

Thử nhiều initial state:

```text
baseline solver
greedy variant A
greedy variant B
randomized greedy
existing solver outputs
```

Sau đó đưa tất cả vào Chokudai Search.

Đặc biệt giữ các initial solution:

```text
C1 PASS
C2 PASS
Udon cao
```

---

# 19. PARAMETER SEARCH

Benchmark có hệ thống:

```text
beam width
Chokudai expansion width
number of iterations
search depth
lookahead depth
destroy size
random seed
evaluation weights
diversity bucket size
```

Không thay nhiều yếu tố cùng lúc mà không log kết quả.

---

# 20. CHECKPOINT

Mỗi lần tìm được improvement:

```text
223
224
225
226
...
```

hãy lưu solution.

Không được chỉ giữ RAM.

Ví dụ:

```text
outputs/best_223.json
outputs/best_224.json
outputs/best_225.json
...
```

Mỗi checkpoint phải:

```text
PASS Criterion 1
PASS Criterion 2
```

---

# 21. VALIDATION

Mỗi candidate best phải chạy official evaluator.

Không tin vào internal heuristic score.

Output report:

```text
Criterion 1: PASS
Criterion 2: PASS
Criterion 3: XXX Udon
```

Nếu internal score và official evaluator khác nhau thì:

```text
official evaluator wins
```

---

# 22. PERFORMANCE

Profile solver.

Tìm bottleneck:

```text
copy state
generate moves
check legality
compute C1/C2
count Udon
hash board
evaluate candidate
```

Ưu tiên:

```text
incremental update
precomputed adjacency
bitset
compact board
cached move list
cached score
```

nếu phù hợp.

Optimization search quality quan trọng hơn micro-optimization ban đầu.

---

# 23. KHÔNG ĐƯỢC LÀM

Không:

```text
❌ viết lại toàn bộ solver mà chưa audit solver cũ

❌ optimize Criterion 3 rồi bỏ qua C1/C2

❌ chấp nhận 230 Udon nếu C1 hoặc C2 fail

❌ chỉ tăng beam width một cách mù quáng

❌ hard-code test case

❌ sửa evaluator để score đẹp hơn

❌ thay đổi luật

❌ báo success dựa trên heuristic nội bộ

❌ claim 230 nếu official evaluator không xác nhận
```

---

# 24. SUCCESS DEFINITION

Target chính:

```text
Criterion 1: PASS
Criterion 2: PASS
Criterion 3: >= 230 Udon
```

Target trung gian vẫn có giá trị:

```text
C1 PASS + C2 PASS + 224
C1 PASS + C2 PASS + 225
C1 PASS + C2 PASS + 226
...
```

Mọi improvement phải được giữ lại.

Không được bỏ solution 228 hợp lệ chỉ vì chưa đạt 230.

---

# 25. OUTPUT CUỐI CÙNG

Sau khi hoàn thành, báo cáo:

## Baseline

```text
Solver:
Algorithm:

Criterion 1:
Criterion 2:
Criterion 3:

Runtime:
```

## Solver mới

```text
Solver:
Algorithm:

Criterion 1:
Criterion 2:
Criterion 3:

Runtime:
```

## Improvement

```text
Udon:
223 → XXX
```

## Những kỹ thuật đã dùng

```text
Chokudai Search:
Greedy:
Beam:
Local Search:
Destroy & Repair:
Lookahead:
State hashing:
Diversity:
Pruning:
```

## Quan trọng nhất

Giải thích:

```text
Điều gì khiến solver vượt được mức 223?
```

Không chỉ nói:

```text
"do Chokudai Search tốt hơn"
```

Phải chỉ ra cụ thể, ví dụ:

```text
baseline chọn placement X quá sớm
→ khóa region Y
→ mất 4 future placements

solver mới giữ alternative state
→ reconstruct region Y
→ thêm 7 Udon
→ vẫn giữ Criterion 1 + Criterion 2
```

---

# FINAL ACCEPTANCE GATE

Chỉ được báo:

```text
SUCCESS
```

khi official evaluator xác nhận:

```text
Criterion 1: PASS
Criterion 2: PASS
Criterion 3: >= 230
```

Nếu chưa đạt 230 nhưng đã vượt 223:

```text
PARTIAL SUCCESS

Best valid solution:
Criterion 1: PASS
Criterion 2: PASS
Criterion 3: XXX
```

Sau đó tiếp tục tập trung search quanh best valid solution thay vì quay lại từ đầu.

## TƯ DUY TỐI ƯU CUỐI CÙNG

Bài toán không phải:

```text
maximize Udon at all costs
```

mà là:

```text
maximize Udon
SUBJECT TO
Criterion 1 satisfied
AND
Criterion 2 satisfied
```

Tức là:

```text
C1 + C2 = feasibility constraints
C3 = optimization objective
```

Mục tiêu cuối:

```text
VALID(C1, C2)
+
MAXIMIZE(C3)
+
TARGET >= 230 UDON
```
# 26. AGENT LEARNING SYSTEM — BẮT BUỘC

Không được làm việc theo chu trình:

```text
đọc code
→ nghĩ một ý tưởng
→ sửa code
→ chạy
→ không tốt
→ nghĩ ý tưởng khác
```

vì cách này rất dễ lặp lại cùng một sai lầm.

Thay vào đó, hãy xây dựng một **Experiment Learning Loop** để agent tích lũy kiến thức sau mỗi lần benchmark.

Mục tiêu:

```text
Experiment
    ↓
Measurement
    ↓
Analysis
    ↓
Knowledge extraction
    ↓
Next hypothesis
    ↓
Better experiment
```

Agent phải trở nên có thông tin hơn sau mỗi iteration.

---

# 27. TẠO EXPERIMENT MEMORY

Tạo một file riêng, ví dụ:

```text
solver_learning/
    experiment_log.jsonl
    knowledge_base.md
    elite_solutions.json
    failed_patterns.json
    parameter_results.csv
```

Không dùng memory nằm trong đầu agent.

Mọi kiến thức quan trọng phải được ghi ra file để iteration sau có thể đọc lại.

---

# 28. EXPERIMENT LOG

Mỗi lần chạy một solver/configuration, ghi một record.

Ví dụ:

```json
{
  "experiment_id": 17,

  "parent": 14,

  "solver": "chokudai_destroy_repair_v3",

  "changes": [
    "destroy_size 2 -> 3",
    "future_potential weight 0.3 -> 0.5"
  ],

  "parameters": {
    "beam_width": 128,
    "expand_per_depth": 16,
    "destroy_size": 3,
    "lookahead": 2
  },

  "criterion_1": true,
  "criterion_2": true,

  "udon": 226,

  "runtime_ms": 4812,

  "states_expanded": 82341,

  "unique_states": 61723,

  "best_found_at_ms": 3014,

  "notes": [
    "improvement mainly occurred in region 4",
    "larger destroy recovered 3 additional placements"
  ]
}
```

Không được chỉ ghi:

```text
run 17 = 226
```

Phải biết:

```text
226 đến từ thay đổi nào?
```

---

# 29. HYPOTHESIS → EXPERIMENT → CONCLUSION

Trước mỗi thay đổi đáng kể, agent phải ghi hypothesis.

Ví dụ:

```text
Hypothesis H12:

Baseline bị kẹt ở 223 vì local region R5
có 2 placement sớm khóa 4 candidate placement khác.

Nếu remove 2 placement đó
và dùng Chokudai để rebuild vùng R5,
Udon có thể tăng ít nhất +2
mà không ảnh hưởng Criterion 1/2.
```

Sau đó mới chạy experiment.

Kết quả:

```text
H12 result:

223 → 225

C1 PASS
C2 PASS

Hypothesis supported.
```

Hoặc:

```text
223 → 222

Hypothesis rejected.

Reason:
destroy region làm mất một structural condition của Criterion 2.
```

Sau đó lưu kết luận.

Không được thử lại cùng hypothesis thất bại trừ khi có thay đổi bản chất.

---

# 30. KNOWLEDGE BASE

Sau mỗi nhóm experiment, cập nhật:

```text
solver_learning/knowledge_base.md
```

Format:

```text
# Proven useful techniques

- Destroy size 2–4 hoạt động tốt quanh solution >=223.
- Lookahead 2 tốt hơn lookahead 1 ở constrained regions.
- Beam width >256 không tạo improvement đáng kể.
- Criterion 2 thường bị phá khi region X bị reconstruct tự do.
- Keeping candidate mobility >8 giúp tránh dead-end.

# Proven bad techniques

- Pure greedy immediate-Udon ranking.
- Destroy size >8.
- Random mutation toàn board.
- evaluator chỉ dùng current_udon.

# Unknown

- Whether region-aware Chokudai improves 226.
- Whether constrained-first ordering helps late game.
```

Agent phải đọc file này trước khi đề xuất experiment tiếp theo.

---

# 31. ELITE ARCHIVE

Không chỉ giữ một best solution.

Giữ một tập:

```text
Elite Archive
```

Ví dụ:

```text
E1 = 226 Udon
E2 = 225 Udon
E3 = 225 Udon
E4 = 224 Udon
```

Nhưng các solution phải **khác nhau về cấu trúc**.

Không giữ:

```text
20 solution gần như giống hệt nhau.
```

Có thể tính similarity bằng:

```text
placement overlap
board hash distance
region signature
move difference
```

Ví dụ:

```text
similarity(A, B) > 0.98
```

thì chỉ giữ solution tốt hơn.

Mục đích:

```text
một local optimum có thể kẹt ở 226

nhưng một elite khác chỉ có 224
lại nằm trong basin có thể đi tới 230.
```

---

# 32. FAILURE MEMORY

Agent phải học cả từ solution thất bại.

Tạo:

```text
failed_patterns.json
```

Ví dụ:

```json
{
  "pattern": "destroy_region_7_large",
  "effect": "criterion_2_fail",
  "frequency": 9,
  "likely_reason": "removes mandatory connection structure"
}
```

Hoặc:

```json
{
  "pattern": "greedy_high_immediate_udon",
  "effect": "dead_end_around_222_224",
  "frequency": 14
}
```

Trước khi tạo candidate mới, kiểm tra failure memory.

Nếu candidate giống pattern đã thất bại nhiều lần:

```text
downrank
```

hoặc:

```text
skip
```

---

# 33. MOVE-LEVEL LEARNING

Không chỉ học ở mức solver.

Nếu feasible, ghi lại hiệu quả của từng loại move.

Ví dụ:

```text
move feature:
- immediate_udon
- blocked_cells_after_move
- mobility_after_move
- constrained_neighbors
- region_fragmentation
- criterion2_margin
```

Sau nhiều experiment, thống kê:

```text
moves dẫn tới elite solution thường có đặc điểm gì?
```

Ví dụ agent có thể phát hiện:

```text
Immediate Udon = +1
nhưng mobility giảm >40%
→ thường dẫn tới dead-end.
```

Từ đó cập nhật move ordering.

Không cần Machine Learning model phức tạp ngay.

Ban đầu có thể dùng thống kê:

```text
average future improvement
success rate
elite frequency
```

---

# 34. STATE FEATURE ANALYSIS

Với các solution:

```text
223
224
225
226...
```

hãy trích xuất feature.

Ví dụ:

```text
udon_count
legal_moves
number_of_regions
largest_empty_region
blocked_cells
mobility
candidate_count
fragmentation
criterion1_margin
criterion2_margin
```

Sau đó so sánh.

Ví dụ:

```text
223 dead-end:
legal_moves = 3
fragmentation = 9

225 elite:
legal_moves = 11
fragmentation = 5
```

Kết luận:

```text
mobility và fragmentation
có thể dự báo future potential tốt hơn current_udon đơn thuần.
```

Dùng insight này để cải thiện evaluator.

---

# 35. ABLATION TEST

Khi solver tốt hơn, không được lập tức kết luận mọi thành phần đều hữu ích.

Ví dụ solver mới gồm:

```text
Chokudai
+ lookahead
+ destroy repair
+ mobility heuristic
+ diversity
```

Chạy ablation:

```text
full                  = 227

without lookahead     = 224
without diversity     = 227
without mobility      = 223
without destroy       = 225
```

Kết luận:

```text
mobility heuristic: critical
lookahead: useful
destroy repair: useful
diversity: currently neutral
```

Như vậy agent biết nên tiếp tục tối ưu phần nào.

---

# 36. PARAMETER LEARNING

Không brute-force tất cả tổ hợp.

Xây một parameter history.

Ví dụ:

```text
beam_width:

32  → best 223
64  → best 225
128 → best 226
256 → best 226
512 → best 226
```

Agent phải kết luận:

```text
128 là vùng đáng tập trung.
```

Không tiếp tục thử:

```text
1024
2048
4096
```

nếu không có evidence.

Tương tự với:

```text
destroy_size
lookahead_depth
expansion_width
random_restart
mobility_weight
future_weight
```

---

# 37. EXPLORE VS EXPLOIT

Mỗi batch experiment nên chia roughly:

```text
70% EXPLOIT
30% EXPLORE
```

EXPLOIT:

```text
tối ưu quanh best hiện tại
```

Ví dụ best = 226:

```text
226
→ local destroy
→ parameter tuning
→ targeted lookahead
```

EXPLORE:

```text
thử basin khác
```

Ví dụ:

```text
start từ elite 224 khác biệt
randomized greedy
different move ordering
alternative region strategy
```

Nếu tất cả experiment chỉ quanh một best solution thì rất dễ mắc local optimum.

---

# 38. STAGNATION DETECTOR

Theo dõi:

```text
iterations_without_improvement
```

Ví dụ:

```text
if no improvement for 20 meaningful experiments:
```

không tiếp tục tinh chỉnh cùng một configuration.

Chuyển strategy.

Ví dụ:

```text
parameter tuning
        ↓ stagnates
destroy & repair
        ↓ stagnates
multi-start
        ↓
alternative evaluator
```

Tạo rule:

```text
STAGNATION_LEVEL_1:
no improvement 10 experiments
→ change parameters

STAGNATION_LEVEL_2:
no improvement 20 experiments
→ change neighborhood/search strategy

STAGNATION_LEVEL_3:
no improvement 40 experiments
→ analyze elite structures and redesign heuristic
```

Không hard-code chính xác 10/20/40 nếu runtime thực tế cho thấy ngưỡng khác hợp lý.

---

# 39. REGION-BASED LEARNING

Nếu board có thể chia thành vùng, agent phải học region nào là bottleneck.

Tạo:

```text
region_stats
```

Ví dụ:

| Region | Current Udon | Potential | Failed rebuilds | Successful rebuilds |
|---|---:|---:|---:|---:|
| R1 | 28 | +0 | 7 | 0 |
| R2 | 31 | +1 | 4 | 1 |
| R3 | 19 | +4 | 2 | 6 |

Từ đây:

```text
R3
```

nên được ưu tiên search hơn R1.

Không waste search budget vào vùng đã gần tối ưu nếu vùng khác còn nhiều potential.

---

# 40. DIFFERENCE ANALYSIS GIỮA ELITE SOLUTIONS

Nếu có:

```text
Solution A = 225
Solution B = 226
```

không chỉ nhìn score.

Diff placement:

```text
A-only placements
B-only placements
common placements
```

Sau đó tìm:

```text
thay đổi cấu trúc nào tạo +1?
```

Tương tự:

```text
223 vs 226
```

Agent phải cố gắng rút ra rule tổng quát.

Ví dụ:

```text
226 tránh placement pattern P
ở early game.

Pattern P xuất hiện trong:
223
224
225

nhưng không xuất hiện ở:
226
```

→ pattern P có thể là local trap.

---

# 41. PATH ANALYSIS

Không chỉ lưu final board.

Nếu có thể, lưu sequence:

```text
state0
move1
state1
move2
...
best
```

Khi một branch đạt improvement:

```text
223 → 226
```

hãy xác định:

```text
điểm rẽ quan trọng đầu tiên
```

so với baseline.

Ví dụ:

```text
baseline:
move 87 = X

elite:
move 87 = Y
```

Sau đó từ state trước move 87:

```text
search intensively
```

Đây thường hiệu quả hơn search lại toàn bộ board.

---

# 42. CRITICAL DECISION MINING

So sánh nhiều elite path và tìm những move có ảnh hưởng lớn.

Ví dụ:

```text
Move M xuất hiện trong:
90% solution >=225

nhưng chỉ:
15% solution <=223
```

Có thể xem M là:

```text
promising structural decision
```

Ngược lại:

```text
Move N xuất hiện trong:
80% dead-end
5% elite
```

→ downrank N.

Không biến thành hard rule ngay.

Chỉ dùng như heuristic trừ khi đã chứng minh bắt buộc.

---

# 43. AUTOMATIC HEURISTIC UPDATE

Sau một số lượng experiment đủ lớn, agent có thể cập nhật evaluator dựa trên evidence.

Ví dụ evaluator cũ:

```text
score =
    udon * 10
  + mobility * 1
  - fragmentation * 0.5
```

Experiment cho thấy mobility rất quan trọng.

Thử:

```text
score =
    udon * 10
  + mobility * 2
  - fragmentation * 0.8
```

Nhưng mọi update phải:

```text
1. có hypothesis
2. benchmark
3. compare baseline
4. ablation nếu tốt hơn
```

Không tự điều chỉnh weight liên tục mà không ghi log.

---

# 44. TWO-LEVEL SEARCH

Khuyến nghị kiến trúc:

```text
LEVEL 1 — Macro search
```

Chọn:

```text
region nào cần rebuild
placements nào cần destroy
elite solution nào làm parent
```

Sau đó:

```text
LEVEL 2 — Micro search
```

Chokudai Search tối ưu cách rebuild vùng đó.

Ví dụ:

```text
Elite 226
    ↓
Macro:
choose region R3
destroy 3 placements
    ↓
Micro Chokudai:
search 50,000 candidate reconstructions
    ↓
candidate 227
```

Điều này tốt hơn việc Chokudai search toàn bộ state-space một cách mù quáng.

---

# 45. BANDIT-STYLE STRATEGY SELECTION

Nếu có nhiều strategy:

```text
S1 = Chokudai
S2 = destroy-2
S3 = destroy-3
S4 = local swap
S5 = randomized greedy
S6 = region rebuild
```

ghi lại:

```text
attempt count
improvement count
average gain
best gain
runtime
```

Ví dụ:

| Strategy | Attempts | Improvements | Avg Gain |
|---|---:|---:|---:|
| destroy-2 | 20 | 5 | +0.40 |
| destroy-5 | 20 | 0 | 0 |
| region rebuild | 12 | 6 | +0.75 |

Agent nên phân bổ nhiều search budget hơn cho:

```text
region rebuild
```

nhưng vẫn giữ một phần exploration cho strategy khác.

Không cần implement formal UCB/Thompson Sampling nếu không cần.

Một scheduler adaptive đơn giản là đủ.

---

# 46. BEST-SOLUTION FAMILY

Không chỉ lưu:

```text
BEST = 226
```

Hãy lưu:

```text
Best overall valid
Best by structural family
Best by region configuration
Best by search strategy
```

Ví dụ:

```text
global best       = 226
greedy family     = 224
chokudai family   = 226
region family R3  = 225
random family     = 224
```

Điều này giúp tránh mất diversity khi một family tạm thời dẫn đầu.

---

# 47. REPRODUCIBILITY

Mọi experiment stochastic phải log:

```text
random_seed
```

Ví dụ:

```text
seed = 12345
```

Nếu tìm được 228:

```text
phải chạy lại đúng seed
```

và verify reproducible.

Sau đó thử seed khác để kiểm tra thuật toán thực sự tốt hơn hay chỉ lucky run.

---

# 48. CONFIDENCE LEVEL

Phân biệt:

```text
ONE lucky run
```

và:

```text
consistent improvement
```

Ví dụ:

```text
solver A:
223
223
223
230
223
```

khác với:

```text
solver B:
228
229
228
229
230
```

Nếu time limit của contest quan trọng, consistency phải được báo cáo.

Nhưng final objective vẫn là official score tốt nhất hợp lệ theo luật.

---

# 49. LEARNING LOOP BẮT BUỘC

Agent phải lặp theo pipeline:

```text
1. LOAD knowledge_base

2. LOAD experiment history

3. LOAD elite solutions

4. ANALYZE current best

5. IDENTIFY bottleneck

6. FORM hypothesis

7. SELECT smallest meaningful experiment

8. RUN experiment

9. VALIDATE Criterion 1

10. VALIDATE Criterion 2

11. MEASURE Udon

12. COMPARE against parent

13. RECORD result

14. UPDATE knowledge_base

15. UPDATE elite archive

16. SELECT next hypothesis
```

Không được bỏ qua:

```text
13
14
15
```

vì đó chính là phần khiến agent "học".

---

# 50. ITERATIVE TARGETS

Thay vì chỉ nhìn:

```text
223 → 230
```

hãy coi:

```text
223 → 224
224 → 225
225 → 226
226 → 227
227 → 228
228 → 229
229 → 230
```

là các learning milestone.

Mỗi lần đạt milestone mới:

```text
freeze solution
analyze difference
extract knowledge
```

Trước khi tiếp tục.

---

# 51. SPECIAL MODE KHI ĐẠT 227+

Khi best valid solution >=227:

giảm exploration diện rộng.

Chuyển sang:

```text
targeted neighborhood optimization
```

Ưu tiên:

```text
critical region detection
1→2 replacement
2→3 replacement
3→4 replacement
small destroy & repair
alternative local ordering
```

Không restart toàn board quá thường xuyên.

Mục tiêu lúc này không phải tìm một kiến trúc hoàn toàn mới mà là:

```text
+1
+1
+1
```

---

# 52. SPECIAL MODE KHI ĐẠT 229

Khi:

```text
C1 PASS
C2 PASS
Udon = 229
```

tạo một mode riêng:

```text
ONE-UDON SEARCH
```

Phân tích toàn bộ board để tìm:

```text
một blocked placement
một local conflict
một 1→2 exchange
một region có theoretical +1
```

Search neighborhood rất sâu quanh các điểm đó.

Không waste budget vào toàn board nếu chỉ cần thêm 1 Udon.

---

# 53. UPPER-BOUND ESTIMATION

Nếu có thể, xây upper bound cho mỗi region/state.

Ví dụ:

```text
current_udon
+
maximum_possible_remaining_udon
```

Nếu:

```text
upper_bound <= current_best
```

prune.

Đặc biệt khi best = 228:

```text
state upper bound = 227
```

không có lý do search tiếp.

Upper bound không cần perfect.

Chỉ cần:

```text
safe
```

tức là không được underestimate theo cách làm mất optimal candidate.

---

# 54. FINAL AGENT BEHAVIOR

Agent không được hành xử như code generator.

Agent phải hành xử như:

```text
researcher
+
optimization engineer
+
solver competitor
```

Mỗi thay đổi cần trả lời được:

```text
Tại sao tôi thử điều này?

Evidence nào khiến tôi tin nó đáng thử?

Kết quả cho thấy điều gì?

Tôi học được gì?

Experiment tiếp theo nên thay đổi yếu tố nào?
```

Không được kết luận dựa trên intuition nếu đã có benchmark phản bác intuition đó.

---

# 55. SUCCESS LEARNING REPORT

Khi kết thúc, ngoài score report phải có:

## Starting point

```text
C1: PASS
C2: PASS
Udon: 223
```

## Final

```text
C1: PASS
C2: PASS
Udon: XXX
```

## Learning trajectory

```text
223
↓
224 — discovered ...
↓
226 — changed ...
↓
228 — region ...
↓
230 — final improvement ...
```

## Most valuable discoveries

Liệt kê tối đa những insight thực sự được benchmark chứng minh.

Ví dụ:

```text
1. Immediate-Udon greedy causes late-game fragmentation.

2. Destroy size 3 around constrained regions consistently
   outperformed global restart.

3. Mobility was a stronger predictor of future improvement
   than raw current Udon between scores 220–226.

4. Chokudai preserved an alternative branch that ordinary
   beam search discarded at depth 87.

5. Final +2 came from replacing two early placements with
   three placements in region R4.
```

## Failed ideas

Cũng phải báo cáo:

```text
idea
reason failed
evidence
```

để lần sau không lặp lại.

---

# FINAL PRINCIPLE

Agent phải tối ưu không chỉ:

```text
solution score
```

mà còn tối ưu:

```text
knowledge gained per experiment
```

Một experiment không tăng Udon vẫn có giá trị nếu nó chứng minh rõ:

```text
một hướng không hiệu quả
```

và giúp giảm không gian tìm kiếm.

Mục tiêu cuối cùng:

```text
C1 PASS
+
C2 PASS
+
maximize Udon
+
experiment-driven learning
+
target >= 230
```