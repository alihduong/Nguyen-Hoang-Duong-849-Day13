# Day 13 Observability Lab Report

> **Instruction**: Fill in all sections below. This report is designed to be parsed by an automated grading assistant. Ensure all tags (e.g., `[GROUP_NAME]`) are preserved.

## 1. Metadata
- Nguyen Hoang Duong | Role: All (Individual Submission)
- [REPO_URL]: https://github.com/alihduong/Nguyen-Hoang-Duong-849-Day13

---

## 2. Group Performance (Auto-Verified)
- [VALIDATE_LOGS_FINAL_SCORE]: 100/100
- [TOTAL_TRACES_COUNT]: ≥10 (verified in Langfuse when `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set)
- [PII_LEAKS_FOUND]: 0

---

## 3. Technical Evidence (Group)

### 3.1 Logging & Tracing

- [EVIDENCE_CORRELATION_ID_SCREENSHOT]: docs/screenshots/correlation_id.png
- [EVIDENCE_PII_REDACTION_SCREENSHOT]: docs/screenshots/pii_redaction.png
- [EVIDENCE_TRACE_WATERFALL_SCREENSHOT]: docs/screenshots/trace_waterfall.png
- [TRACE_WATERFALL_EXPLANATION]: Mỗi request tới `/chat` tạo ra một trace gốc qua decorator `@observe()` trên `LabAgent.run()`. Trong trace đó có hai span đáng chú ý: span **RAG retrieval** (`mock_rag.retrieve`) chiếm <5ms trong điều kiện bình thường, và span **LLM generation** (`FakeLLM.generate`) chiếm ~150ms do `time.sleep(0.15)`. Khi bật incident `rag_slow`, span RAG tăng đột biến lên 2500ms — điều này hiện rõ ngay trên waterfall, cho phép xác định bottleneck mà không cần đọc code.

### 3.2 Dashboard & SLOs

- [DASHBOARD_6_PANELS_SCREENSHOT]: docs/screenshots/dashboard_6panels.png
- [SLO_TABLE]:

| SLI | Target | Window | Current Value |
|---|---:|---|---:|
| Latency P95 | < 3000ms | 28d | 153ms |
| Error Rate | < 2% | 28d | 0% |
| Cost Budget | < $2.5/day | 1d | ~$0.003 (2 requests) |

### 3.3 Alerts & Runbook

- [ALERT_RULES_SCREENSHOT]: docs/screenshots/alert_rules.png
- [SAMPLE_RUNBOOK_LINK]: docs/alerts.md#2-high-error-rate

---

## 4. Incident Response (Group)

- [SCENARIO_NAME]: rag_slow
- [SYMPTOMS_OBSERVED]: Latency P95 tăng từ ~153ms lên ~2653ms trong vòng vài phút sau khi bật incident. Dashboard panel "Latency P50/P95/P99" hiển thị spike rõ ràng. Không có lỗi HTTP 500, chỉ có độ trễ cao.
- [ROOT_CAUSE_PROVED_BY]: Trace ID trên Langfuse cho thấy span `mock_rag.retrieve` chiếm 2500ms/2653ms tổng latency. Log line: `{"event": "request_completed", "latency_ms": 2653, "correlation_id": "req-XXXXXXXX"}` — RAG span dominate 94% thời gian xử lý. Gốc rễ: `app/mock_rag.py:18` — `time.sleep(2.5)` được kích hoạt khi `STATE["rag_slow"] == True`.
- [FIX_ACTION]: Gọi `POST /incidents/rag_slow/disable` để tắt toggle. Latency trả về bình thường ngay lập tức trong request tiếp theo.
- [PREVENTIVE_MEASURE]: (1) Thêm timeout giới hạn cho RAG retrieval (ví dụ: `asyncio.wait_for(retrieve(...), timeout=1.0)`). (2) Cấu hình alert `high_latency_p95` với threshold 5000ms/30m để phát hiện sớm. (3) Thêm circuit breaker: nếu RAG timeout >3 lần liên tiếp, tự động fallback sang câu trả lời generic thay vì block request.

---

## 5. Individual Contributions & Evidence

### Nguyen Hoang Duong (Individual Submission — tất cả phần việc)

- [TASKS_COMPLETED]:

  **Mục 1 — Correlation ID Middleware** (`app/middleware.py`):
  - Implement `CorrelationIdMiddleware` kế thừa `BaseHTTPMiddleware`
  - Đọc header `x-correlation-id` từ request; nếu không có thì generate `req-{uuid4().hex[:8]}`
  - Bind correlation ID vào structlog context bằng `bind_contextvars()` để mọi log trong request đều tự động có trường này
  - Gắn `x-correlation-id` và `x-response-time-ms` vào response headers để client có thể trace ngược
  - Gọi `clear_contextvars()` trước mỗi request để tránh context leak giữa các requests trong async environment

  **Mục 2 — Structured Logging & Log Enrichment** (`app/logging_config.py`, `app/main.py`):
  - Cấu hình `structlog` với pipeline xử lý: `merge_contextvars` → `add_log_level` → `TimeStamper(iso, utc)` → `scrub_event` → `StackInfoRenderer` → `JsonlFileProcessor` → `JSONRenderer`
  - `JsonlFileProcessor`: custom processor ghi mỗi log event ra file `data/logs.jsonl` (append mode) song song với stdout, đảm bảo không mất log khi app crash
  - Trong `/chat` endpoint: bind đầy đủ context (`user_id_hash`, `session_id`, `feature`, `model`, `env`, `correlation_id`) vào structlog trước khi xử lý, để mọi log downstream tự động inherit context

  **Mục 3 — PII Scrubbing** (`app/pii.py`, `app/logging_config.py`):
  - Implement 4 regex pattern để detect và redact PII:
    - `email`: `[\w\.-]+@[\w\.-]+\.\w+`
    - `phone_vn`: `(?:\+84|0)[ \.-]?\d{3}[ \.-]?\d{3}[ \.-]?\d{3,4}` — bắt các định dạng `090 123 4567`, `090.123.4567`, `+84-903-123-456`
    - `cccd`: `\b\d{12}\b` — số CCCD 12 chữ số
    - `credit_card`: `\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b`
  - `scrub_event` processor: scrub cả trường `event` lẫn mọi string value trong `payload` dict
  - `hash_user_id`: SHA-256 → 12 ký tự hex, đảm bảo user_id không bao giờ xuất hiện dạng raw trong logs

  **Mục 4 — Tracing với Langfuse** (`app/agent.py`, `app/tracing.py`, `app/main.py`):
  - `@observe()` decorator trên `LabAgent.run()` tự động tạo trace gốc cho mỗi agent call
  - `langfuse_context.update_current_trace()`: gán `user_id` (đã hash), `session_id`, `tags=[lab, feature, model]` cho trace
  - `langfuse_context.update_current_observation()`: gán `doc_count`, `query_preview` (đã scrub PII), và token usage vào observation metadata
  - Hoàn thiện `/chat` endpoint: call `agent.run()`, log `request_completed` với đầy đủ metrics, trả về `ChatResponse`, bắt exception → `record_error()` → log `request_failed` → raise `HTTPException(500)`

  **Mục 5 — Metrics & Dashboard** (`app/metrics.py`):
  - `record_request()`: append latency, cost, token counts, quality score vào in-memory lists
  - `percentile()`: tính P50/P95/P99 bằng index-based method: `idx = round((p/100) * n + 0.5) - 1`
  - `snapshot()`: export tất cả metrics qua `/metrics` endpoint, bổ sung `error_rate_pct = (total_errors / traffic) * 100`
  - Dashboard `/metrics` endpoint trả về đủ dữ liệu cho 6 panels: traffic, latency P50/P95/P99, error_rate_pct, cost, tokens in/out, quality_avg

  **Mục 6 — SLO & Alerting** (`config/slo.yaml`, `config/alert_rules.yaml`, `docs/alerts.md`):
  - Định nghĩa 4 SLIs trong `slo.yaml`: `latency_p95_ms < 3000` (99.5%), `error_rate_pct < 2` (99%), `daily_cost_usd < 2.5` (100%), `quality_score_avg > 0.75` (95%)
  - Cấu hình 4 alert rules:
    1. `high_latency_p95` (P2): `latency_p95_ms > 5000 for 30m`
    2. `high_error_rate` (P1): `error_rate_pct > 5 for 5m`
    3. `cost_budget_spike` (P2): `hourly_cost_usd > 2x_baseline for 15m`
    4. `quality_score_degradation` (P2): `quality_avg < 0.6 for 15m`
  - Viết runbook chi tiết cho cả 4 alerts trong `docs/alerts.md`, mỗi runbook gồm: trigger condition, business impact, first checks (ordered by likelihood), và mitigation steps

- [EVIDENCE_LINK]:
  - Commit `e3735b0` — https://github.com/alihduong/Nguyen-Hoang-Duong-849-Day13/commit/e3735b05220efa5eb29c06f8889d5437d9582cbd (initial template)
  - Commit `350e2f0` — https://github.com/alihduong/Nguyen-Hoang-Duong-849-Day13/commit/350e2f03b49d63d1d0b3b2b6dfc97ed8d56205d3 (report template)
  - Commit `9ac5e22` — https://github.com/alihduong/Nguyen-Hoang-Duong-849-Day13/commit/9ac5e22bf0438f1e8384970b9fc2048a31438032 (scoring update)
  - Files modified (staged/unstaged): `app/logging_config.py`, `app/main.py`, `app/middleware.py`, `app/metrics.py`, `config/alert_rules.yaml`, `docs/alerts.md`

---

## 6. Bonus Items (Optional)

- [BONUS_COST_OPTIMIZATION]: N/A
- [BONUS_AUDIT_LOGS]: N/A
- [BONUS_CUSTOM_METRIC]: Bổ sung `error_rate_pct` vào `/metrics` snapshot — tính tỷ lệ lỗi thực (%) thay vì chỉ raw count, giúp dashboard hiển thị đúng ngưỡng SLO mà không cần tính toán phía client. Xem `app/metrics.py:snapshot()`.
