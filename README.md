# 🚀 QueueStorm Investigator

### AI/API SupportOps Challenge – SUST CSE Carnival 2026

A fast, deterministic API that investigates digital finance support tickets by combining customer complaints with transaction history.

Unlike a traditional classifier, QueueStorm **reasons from evidence**. It identifies the relevant transaction, determines whether the complaint is supported by the available data, routes the case to the correct department, and generates a safe, professional customer response.

---

## ✨ Key Features

* ⚡ Deterministic evidence reasoning
* 🔍 Transaction matching from complaint + history
* 🛡️ Built-in fintech safety guardrails
* 🌐 English & Bangla complaint support
* 📄 Strict JSON schema compliance
* 🚀 Zero external dependencies during inference
* 💰 $0 inference cost
* 🧪 102 automated tests

---

# 🌐 Live Demo

| Service        | URL                                                     |
| -------------- | ------------------------------------------------------- |
| Base URL       | https://chatbot-backend-production-7fe7.up.railway.app  |
| Health Check   | `/health`                                               |
| Analyze Ticket | `POST /analyze-ticket`                                  |
| Docker Image   | `docker pull maruf52230/queuestorm-investigator:latest` |

Health endpoint:

```bash
curl https://chatbot-backend-production-7fe7.up.railway.app/health
```

Response

```json
{
  "status":"ok"
}
```

---

# 🏗 Architecture

```text
Client
   │
   ▼
FastAPI
   │
   ▼
Input Validation
   │
   ▼
Evidence Reasoning Engine
   │
   ├── Complaint Classification
   ├── Transaction Matching
   ├── Evidence Verification
   ├── Department Routing
   ├── Severity Assignment
   └── Human Review Decision
   │
   ▼
Safety Guard
   │
   ▼
JSON Response
```

---

# 🧠 Reasoning Pipeline

The service follows five deterministic steps.

### 1. Complaint Classification

Detects:

* Wrong Transfer
* Payment Failed
* Refund Request
* Duplicate Payment
* Merchant Settlement Delay
* Agent Cash-in Issue
* Phishing / Social Engineering
* Other

Supports:

* English
* Bangla
* Banglish

---

### 2. Evidence Matching

Finds the transaction referred to by the complaint using:

* Amount
* Time
* Counterparty
* Transaction type
* Status

Normalizes:

* Bangla numerals
* 5k / 5 thousand / ৫ লাখ
* Mixed-language complaints

---

### 3. Evidence Verification

Returns one of:

* consistent
* inconsistent
* insufficient_data

The system **never guesses** when evidence is missing.

---

### 4. Routing

Determines

* Department
* Severity
* Human Review Requirement

using deterministic rules.

---

### 5. Safe Response Generation

Produces

* Agent Summary
* Recommended Next Action
* Customer Reply

using safe templates.

---

# 🛡 Safety Guardrails

Every response is validated before being returned.

✔ Never asks for

* OTP
* PIN
* Password
* Full Card Number

✔ Never promises

* Refund
* Reversal
* Account Unblock

✔ Ignores prompt injection

✔ Directs users only to official support channels

---

# ⚙ Technology Stack

| Component  | Technology  |
| ---------- | ----------- |
| Backend    | FastAPI     |
| Language   | Python 3.12 |
| Validation | Pydantic v2 |
| Server     | Uvicorn     |
| Testing    | Pytest      |
| Deployment | Railway     |
| Container  | Docker      |

---

# 🚀 Running Locally

## Docker

```bash
docker pull maruf52230/queuestorm-investigator:latest

docker run --rm -p 8000:8000 maruf52230/queuestorm-investigator:latest
```

---

## Python

```bash
cd backend

pip install -r requirements.txt

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

# 📬 Example Request

```json
{
  "ticket_id":"TKT-001",
  "complaint":"I sent 5000 taka to the wrong number.",
  "transaction_history":[
    {
      "transaction_id":"TXN-9101",
      "amount":5000,
      "status":"completed"
    }
  ]
}
```

---

# ✅ Example Response

```json
{
  "ticket_id":"TKT-001",
  "relevant_transaction_id":"TXN-9101",
  "evidence_verdict":"consistent",
  "case_type":"wrong_transfer",
  "severity":"high",
  "department":"dispute_resolution",
  "agent_summary":"Customer reports the transaction was sent to the wrong recipient.",
  "recommended_next_action":"Verify transaction details and initiate the dispute workflow.",
  "customer_reply":"We have received your request and our support team will review it through official channels. Please do not share your PIN or OTP with anyone.",
  "human_review_required":true,
  "confidence":0.95
}
```

---

# 🧪 Testing

```bash
pytest
```

Coverage includes

* API Contract
* Evidence Reasoning
* Hidden Edge Cases
* Safety Validation
* Robustness
* Performance
* Reliability

**102 automated tests**

---

# 💰 Models & Cost

No external LLM is used.

The solution is a deterministic rule engine.

Benefits

* Zero inference cost
* No API keys
* No network dependency
* Extremely low latency
* Fully reproducible outputs

---

# 📈 Performance

* Average response time: **<100 ms**
* No outbound network calls
* Stateless API
* Deterministic responses
* Production-ready Docker image

---

# Known Limitations

* Fully written amounts ("five thousand") fall back to `insufficient_data`.
* Unsupported complaint categories are safely mapped to `other`.
* Bangla responses use deterministic templates instead of generative text.

---

# Repository Structure

```
backend/
tests/
sample_output.json
RUNBOOK.md
README.md
Dockerfile
docker-compose.yml
requirements.txt
```

---

# License

Developed for the **SUST CSE Carnival 2026 – QueueStorm Investigator Hackathon**.
