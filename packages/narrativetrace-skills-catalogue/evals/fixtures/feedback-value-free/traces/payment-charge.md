---
type: trace
run: shiny mink ships
scenario: The auth token is redacted and the other arguments survive
entry_point: PaymentService.charge
duration_ms: 0
trace_id: fb57de883928d063727e4a3b5e08e0f3
trace_name: milky snow sways
method_count: 2
error_count: 0
---

## Trace: milky snow sways — PaymentService.charge

**Scenario:** The auth token is redacted and the other arguments survive
**Duration:** 0ms | **Result:** PASSED

### Call Flow

- **PaymentService.charge**(customer_id: `"C-1234"`, auth_token: `[REDACTED]`, amount: `"42.00"`) — 0ms #1
  - **GatewayClient.authorize**(merchant_id: `"M-77"`, gateway_ref: `"ghp_NTCANARY0001"`) → `"AUTH-OK"` — 0ms #1.1
  - → `"PAY-C-1234"`
