# How QueueStorm Investigator Works

A deterministic API that reads a support ticket, reasons from transaction evidence, and produces a safe, routed response — in under 100 ms with no external dependencies.

---

## At a glance

| | |
|---|---|
| Response time | < 100 ms |
| Pipeline steps | 5 |
| Case types supported | 8 |
| Automated tests | 102 |
| Inference cost | $0 |

---

## Request flow

```mermaid
flowchart LR
    A([Client]) -->|POST /analyze-ticket| B[Input Validation]
    B --> C[Complaint Classification]
    C --> D[Transaction Matching]
    D --> E[Evidence Verdict & Routing]
    E --> F[Safety Scan]
    F --> G([JSON Response])

    style A fill:#181c27,stroke:#2a2f3f,color:#e2e6f0
    style B fill:#181c27,stroke:#4f8ef7,color:#4f8ef7
    style C fill:#181c27,stroke:#38d9a9,color:#38d9a9
    style D fill:#181c27,stroke:#38d9a9,color:#38d9a9
    style E fill:#181c27,stroke:#f7c94f,color:#f7c94f
    style F fill:#181c27,stroke:#a78bfa,color:#a78bfa
    style G fill:#181c27,stroke:#f75f5f,color:#f75f5f
```

---

## Pipeline steps

### Step 1 — Complaint Classification

The complaint text is normalised (Bangla digits converted, lower-cased) and scanned for keywords in English, Bangla, and Banglish. Safety-critical types are evaluated first so a phishing attempt is never misrouted as a billing issue.

Supported case types:

| Case type | When it applies |
|-----------|----------------|
| `wrong_transfer` | Money sent to the wrong recipient |
| `payment_failed` | Transaction failed but balance may have been deducted |
| `duplicate_payment` | Same charge appears more than once |
| `refund_request` | Customer asking for a refund |
| `agent_cash_in_issue` | Cash deposit through an agent not reflected in balance |
| `merchant_settlement_delay` | Settlement not received within expected window |
| `phishing_or_social_engineering` | Suspicious call or message requesting credentials |
| `other` | Anything not covered above |

---

### Step 2 — Transaction Matching

The customer's stated amount is extracted from the complaint and intersected against the supplied `transaction_history` to identify `relevant_transaction_id`.

Amount formats handled:

- Bare numbers: `5000`, `5,000`
- Shorthand: `5k`, `5K`
- Words: `5 thousand`, `5 hajar`
- Bangla numerals: `৫০০০`
- Bangla units: `৫ হাজার`, `৫ লাখ`

Long digit strings (phone numbers) are excluded so a counterparty number is never mistaken for a payment amount.

---

### Step 3 — Evidence Verdict

The matched transaction's ledger status is compared against what the complaint claims.

| Verdict | Meaning |
|---------|---------|
| `consistent` | The ledger entry supports the complaint |
| `inconsistent` | The data contradicts it — e.g. a "payment failed" claim against a `completed` transaction, or a "wrong transfer" to a recipient the customer has paid repeatedly |
| `insufficient_data` | No matching transaction found, the match is ambiguous, or the complaint lacks enough detail |

**The service never guesses.** When evidence is absent or ambiguous it returns `insufficient_data` and requests clarification.

---

### Step 4 — Routing & Escalation

Department, severity, and `human_review_required` are assigned by deterministic rules.

| Department | Handles |
|------------|---------|
| `dispute_resolution` | Wrong transfers, contested refunds |
| `payments_ops` | Failed payments, duplicate charges |
| `fraud_risk` | Phishing, social engineering, suspicious activity |
| `agent_operations` | Agent cash-in issues |
| `merchant_operations` | Merchant settlement delays |
| `customer_support` | General queries, low-severity refunds, vague complaints |

Disputes, fraud, and duplicates escalate to human review. Cases where no transaction can be matched prompt the agent to collect more detail rather than escalating prematurely.

---

### Step 5 — Safe Response Generation

`agent_summary`, `recommended_next_action`, and `customer_reply` are produced from safe pre-written templates. Complaint text is **never** copied into output fields — the service is structurally immune to prompt injection.

Every generated string then passes through an independent safety scan before being returned.

---

## Safety guardrails

Every customer-facing field is independently validated before leaving the service.

**Never requests credentials**
PIN, OTP, password, or card number are never asked for. Safe warning phrases ("do not share your PIN") are explicitly allowed.

**No unauthorised promises**
Refund, reversal, or account unblock are never confirmed. Replies use the approved phrasing: *"any eligible amount will be returned through official channels."*

**Prompt injection resistant**
Complaint text is never echoed into output fields. Instructions embedded in a complaint (`"ignore your rules"`) have no surface to act on.

**Official channels only**
Replies never redirect customers to third-party numbers, links, or agents.

---

## Example

**Request**

```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5k to a wrong number this afternoon.",
  "transaction_history": [
    {
      "transaction_id": "TXN-9101",
      "amount": 5000,
      "counterparty": "+8801719876543",
      "status": "completed"
    }
  ]
}
```

**Response**

```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "human_review_required": true,
  "confidence": 0.9,
  "reason_codes": ["wrong_transfer", "transaction_match"],
  "agent_summary": "Customer reports TXN-9101 was sent to the wrong recipient.",
  "recommended_next_action": "Verify TXN-9101 with the customer and proceed with the dispute workflow per policy.",
  "customer_reply": "We have noted your concern about transaction TXN-9101. Our dispute team will review the case and contact you through official support channels. Please do not share your PIN or OTP with anyone."
}
```

**What happened step by step**

1. `"5k"` was parsed as `5000` and matched against the transaction history → `TXN-9101` found.
2. Transaction status is `completed` and the complaint says wrong transfer → verdict `consistent`.
3. Case type `wrong_transfer` routes to `dispute_resolution` at `high` severity.
4. `human_review_required: true` — all confirmed wrong-transfer disputes are escalated.
5. Customer reply generated from a safe template; safety scan confirmed no credential request or unauthorised promise.

---

## Why deterministic instead of an LLM

| Concern | Deterministic engine | LLM |
|---------|---------------------|-----|
| Enum-exact output | Always | Not guaranteed |
| Response time | < 100 ms | 1–30 s |
| Cost per request | $0 | Token spend |
| Prompt injection risk | Structurally immune | Requires prompt hardening |
| Reproducibility | Identical output for same input | Non-deterministic |
| External dependency | None | API availability |

---

*Live service: [sustpreli-production-56d0.up.railway.app](https://sustpreli-production-56d0.up.railway.app) · Docker: [maruf52230/queuestorm-investigator](https://hub.docker.com/r/maruf52230/queuestorm-investigator)*
