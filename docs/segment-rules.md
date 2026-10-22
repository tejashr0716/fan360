# Audience Segment Qualification Rules
## Fan360 Audience Intelligence Specification

All segment qualifications are evaluated deterministically in PySpark against the pipeline's configured `as_of_timestamp`.

---

## 1. Segment Definitions

### 1. Engaged Non-Buyers (`engaged_non_buyers`)
- **Business Goal**: Identify highly engaged prospective fans who follow the team digitally but have never converted into paying merchandise customers.
- **Qualification Criteria**:
  1. `valid_completed_order_count == 0` (zero completed purchases with amount > $0).
  2. Number of web engagement events or email actions within the past 90 days (`event_timestamp >= as_of - 90 days`) is $\ge 1$.
- **Boundary Behavior**: Fans whose only activity occurred on day 91 prior to `as_of` do not qualify.
- **Reason Format**: `Has {event_count} activity events in past 90d and 0 completed orders.`

---

### 2. Repeat Buyers (`repeat_buyers`)
- **Business Goal**: Recognize loyal, multi-purchase merchandise customers for exclusive loyalty communications.
- **Qualification Criteria**:
  1. `valid_completed_order_count >= 2`.
  2. Orders must have `order_status = 'COMPLETED'` and `order_amount > 0.00`.
- **Boundary Behavior**: Cancelled, refunded, or pending orders do not increment the count. Exactly 2 valid orders qualifies.
- **Reason Format**: `Placed {completed_orders} completed orders (threshold: >= 2).`

---

### 3. High-Spending Buyers (`high_spending_buyers`)
- **Business Goal**: Identify VIP merchandise fans with high lifetime monetary value.
- **Qualification Criteria**:
  1. `total_valid_spend >= 250.00` in USD.
  2. Sum calculated exclusively over orders with `order_status = 'COMPLETED'` and `order_amount > 0.00`.
- **Boundary Behavior**: Spend of \$249.99 does not qualify. Exactly \$250.00 qualifies.
- **Reason Format**: `Accumulated ${total_spend:.2f} USD in valid completed spend (threshold: >= $250.00).`

---

### 4. Inactive Fans (`inactive_fans`)
- **Business Goal**: Detect dormant fans who have ceased interacting with digital channels and the store for re-engagement or churn prevention.
- **Qualification Criteria**:
  1. `days_since_activity > 180` days relative to `as_of_timestamp`.
  2. Activity considers: web events, email actions, merchandise orders, or account registration date.
  3. Fans with zero recorded events default to account registration date; if account creation is > 180 days ago, they qualify.
- **Boundary Behavior**: A fan active 180 days ago does not qualify (strictly $> 180$ days).
- **Reason Format**: `Last activity was {days_since_activity} days ago (inactivity threshold: > 180d) or never active.`

---

### 5. Abandoned Cart (`abandoned_cart`)
- **Business Goal**: Trigger recovery campaigns for fans who showed purchase intent within the past two weeks without completing the order.
- **Qualification Criteria**:
  1. Fan has at least one web event with `event_type = 'add_to_cart'` and a non-empty `cart_id` within the past 14 days (`event_timestamp >= as_of - 14 days`).
  2. **Resolving Purchase Logic**: There is NO subsequent order placed by that fan matching `cart_id` with `order_status = 'COMPLETED'`.
- **Boundary Behavior**: If a fan added items to `CART_01` 5 days ago, and then placed completed order `ORD_01` for `CART_01` 4 days ago, the cart is resolved and does NOT qualify.
- **Reason Format**: `Unresolved cart {cart_id} created {cart_age_days} days ago without matching order.`

---

## 2. Descriptive Qualification vs Activation Eligibility

| Feature | Descriptive Memberships (`fan_segment_memberships`) | Activation Exports (`activation_audiences`) |
| :--- | :--- | :--- |
| **Audience Scope** | All fans meeting business logic rules | Only fans with verified `OPT_IN` consent |
| **Purpose** | Customer 360 insights, profile exploration, BI reporting | Export to email service providers, ad platforms |
| **Consent Opt-Out** | Fan is retained with `activation_eligible = 0` | **Strictly excluded** (0 records) |
| **Consent None/Missing** | Fan is retained with `activation_eligible = 0` | **Strictly excluded** (0 records) |
| **Consent Withdrawal** | Fan is retained with `activation_eligible = 0` | **Removed from export** on next recomputed run |
