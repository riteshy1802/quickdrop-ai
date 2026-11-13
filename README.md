
# QuickDrop AI

### How it works, some screenshots!

<img width="4089" height="2320" alt="1" src="https://github.com/user-attachments/assets/cb873340-b41a-4797-a607-d602ca84a6a9" />
<img width="4089" height="2320" alt="2" src="https://github.com/user-attachments/assets/dc83788f-8b9c-4edf-897a-d607bc1b1089" />
<img width="4089" height="2320" alt="3" src="https://github.com/user-attachments/assets/fe8bf143-731c-4fc0-b70b-e7fad29c0545" />
<img width="4088" height="2323" alt="4" src="https://github.com/user-attachments/assets/5212cdb7-a144-4975-b826-8cd5c0af5adb" />
<img width="4088" height="2323" alt="5" src="https://github.com/user-attachments/assets/3553df5d-da82-4eaa-9e85-5cea1696fa78" />

### AI-Powered Rider Payout Support & Operations Management

QuickDrop AI is an AI-assisted rider payout support system that handles payment disputes, verifies trip earnings, processes eligible payouts, and escalates complex cases to human operators.

The platform supports **English, Hindi, and Hinglish**, with a dedicated **Rider Interface** and **Operations (Ops) Console**.

Built using **LangGraph**, **Amazon Nova Pro (AWS Bedrock) / Groq**, **FastAPI**, **Next.js**, **PostgreSQL**, **Redis**, and **Docker**, the system combines natural-language understanding with deterministic financial controls.

> **Core principle:** AI understands requests and explains decisions, but never independently authorizes or transfers money. Identity verification, payout calculations, eligibility checks, and payment execution are enforced by deterministic application logic.

**Documentation:** [Payout Policy](docs/policy.md) | [Agent Architecture](backend/docs/agent.md) | [API Contracts](SUBMISSION.md)

---

## 1. Key Features

### AI-Powered Rider Support
- Multilingual support for English, Hindi, and Hinglish.
- LangGraph-based agent workflows for understanding rider queries.
- Amazon Nova Pro or Groq for language understanding and response generation.
- Deterministic verification of rider identity, trip records, and payout eligibility.
- Transparent explanations of earnings calculations and payout decisions.
- Traceable agent execution for auditing and debugging.

### Automated Payout Processing
- Rule-based calculation of rider earnings and dispute amounts.
- Automatic payout authorization for eligible claims up to ₹200.
- Maximum one automatically authorized payout per rider per day.
- Claims exceeding policy limits routed to Ops for approval.
- Transactional reservations and idempotent payment intents.
- Independent background worker for payment processing.
- Provider reconciliation and safe handling of uncertain payment outcomes.

### Operations Console
- Review pending payout approvals and escalations.
- Approve or reject disputed payments.
- Take ownership of support cases.
- Reply directly to riders.
- Add private internal notes.
- Resolve and track support cases.
- Receive real-time updates through Redis Pub/Sub and Server-Sent Events (SSE).

### Reliability & Auditability
- Durable worker architecture.
- Duplicate-request protection.
- Explicit separation of payout authorization and provider settlement.
- Historical evaluation support.
- Traceable payment decisions and agent execution.
- Persistent PostgreSQL and Redis volumes.
- Containerized deployment using Docker Compose.

---

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js |
| Backend API | FastAPI |
| AI Orchestration | LangGraph |
| LLM Providers | Amazon Nova Pro (AWS Bedrock) / Groq |
| Database | PostgreSQL |
| Cache & Real-Time Messaging | Redis |
| Real-Time Delivery | Server-Sent Events (SSE), Redis Pub/Sub |
| Payment Integration | PaySwift Sandbox |
| Database Migrations | Alembic |
| Containerization | Docker & Docker Compose |
| Background Processing | Separate Durable Worker |
| Testing | Backend Tests, Frontend Tests, HTTP Evaluation Suite |

---

## 3. System Architecture

The platform separates AI reasoning, deterministic business rules, payment execution, and human operations.

```text
                  ┌─────────────────────────┐
                  │       Rider UI          │
                  │   Next.js Frontend      │
                  └────────────┬────────────┘
                               │
                               ▼
                  ┌─────────────────────────┐
                  │      FastAPI API        │
                  │  Authentication & HTTP  │
                  └────────────┬────────────┘
                               │
                               ▼
                  ┌─────────────────────────┐
                  │    LangGraph Agent      │
                  │  Nova Pro / Groq LLM    │
                  └────────────┬────────────┘
                               │
                               ▼
                  ┌─────────────────────────┐
                  │   Deterministic Tools   │
                  │                         │
                  │ • Rider verification    │
                  │ • Trip reconciliation   │
                  │ • Earnings calculation  │
                  │ • Policy validation     │
                  │ • Payout authorization  │
                  └────────────┬────────────┘
                               │
                  ┌────────────┴────────────┐
                  │                         │
                  ▼                         ▼
       ┌────────────────────┐   ┌────────────────────┐
       │   PostgreSQL       │   │    Redis           │
       │                    │   │                    │
       │ Trips & Earnings   │   │ Pub/Sub & SSE      │
       │ Cases & Payments   │   │ Real-Time Updates  │
       └──────────┬─────────┘   └────────────────────┘
                  │
                  ▼
       ┌────────────────────┐
       │  Payment Worker    │
       │                    │
       │ Reconciliation     │
       │ Payment Execution  │
       │ Retry Handling     │
       └──────────┬─────────┘
                  │
                  ▼
       ┌────────────────────┐
       │  PaySwift Sandbox  │
       │  Payment Provider  │
       └────────────────────┘

       ┌────────────────────┐
       │    Ops Console     │
       │                    │
       │ Approvals          │
       │ Escalations        │
       │ Human Intervention │
       └────────────────────┘
```

**Important:** The LLM cannot directly move money. All financial operations pass through verified application logic and policy enforcement.

For detailed agent behavior, see [Agent Design](backend/docs/agent.md).

---

## 4. Getting Started

### Prerequisites

Ensure the following are available:

- Docker Desktop with Docker Compose
- AWS Bedrock credentials with access to the configured inference profile, or a Groq API key
- Available host ports for the frontend, backend, PostgreSQL, Redis, and PaySwift
- Administrator credentials for the Ops Console

### Step 1: Configure Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Configure the required variables in `.env`.

```dotenv
# PostgreSQL
POSTGRES_PASSWORD=your_secure_database_password

# Operations Administrator
OPS_ADMIN_EMAIL=admin@example.com
OPS_ADMIN_PASSWORD=your_secure_admin_password

# Rider Session Security
DEMO_SESSION_SECRET=replace_with_a_random_32_character_or_longer_secret
```

Configure one supported LLM provider.

**Option A: Amazon Bedrock (Nova Pro)**

Provide your AWS credentials and select the appropriate Bedrock model/inference profile using the variables documented in `.env.example`.

Temporary AWS credentials also require:

```dotenv
AWS_SESSION_TOKEN=your_temporary_session_token
```

Your IAM identity must have `bedrock:InvokeModel` access to the configured inference profile and required underlying resources.

**Option B: Groq**

Select Groq as the provider using the configuration in `.env.example` and supply:

```dotenv
GROQ_API_KEY=your_groq_api_key
```

> Never commit `.env`, AWS credentials, API keys, or administrator passwords to version control.

### Environment Loading Rules

- Docker Compose loads the root `.env` file.
- An optional `backend/.env` can override duplicate backend environment values.
- Database, Redis, and PaySwift container destinations are explicitly configured in Compose.
- `DEMO_SESSION_SECRET` should be shared and at least 32 characters long so rider sessions survive API restarts.
- Missing optional variables are reported without failing validation.
- The configured LLM provider, database, and administrator settings must pass validation.

### Step 2: Build Docker Images

```bash
docker compose build api frontend
```

### Step 3: Validate Configuration

```bash
docker compose run --rm --no-deps api python -m app.scripts.check_env
```

Resolve any required configuration errors before starting the application.

### Step 4: Start Services

```bash
docker compose up --build -d
```

### Step 5: Seed Initial Data

```bash
docker compose run --rm seed
```

Seeding is explicit and idempotent. Persistent volumes are not reset automatically during startup.

### Step 6: Create the Ops Administrator

```bash
docker compose run --rm api python -m app.scripts.seed_admin
```

### Step 7: Verify Services

```bash
docker compose ps
```

Inspect backend logs:

```bash
docker compose logs --tail=100 api
```

Inspect worker logs:

```bash
docker compose logs --tail=100 worker
```

For further verification instructions, see [Docker Verification](docs/DOCKER_VERIFICATION.md).

---

## 5. Application URLs

After successfully starting the containers:

| Service | URL |
|---|---|
| Rider Portal | http://localhost:3000/rider |
| Operations Console | http://localhost:3000/ops |
| API Health Check | http://localhost:8000/health |

The frontend proxies requests from `/api/backend` to the configured backend destination.

Within Docker:

```text
BACKEND_URL=http://api:8000
```

`BACKEND_URL` is incorporated into Next.js rewrites at image-build time. Rebuild the frontend image when changing this destination.

---

## 6. Docker Services

Docker Compose orchestrates the following components:

| Service | Responsibility |
|---|---|
| `postgres` | Persistent relational data storage |
| `redis` | Pub/Sub and real-time communication |
| `payswift` | Simulated external payment provider |
| Migration Step | Single-owner Alembic database migrations |
| `api` | FastAPI endpoints and agent orchestration |
| `worker` | Durable payment processing and reconciliation |
| `frontend` | Rider and Ops user interfaces |

Internal Docker networking uses:

```text
postgres
redis
payswift
```

When accessing exposed services from the host, use `localhost` and the configured host ports.

For multiple independent deployments, configure:

```dotenv
COMPOSE_PROJECT_NAME=quickdrop_local
```

Also configure the five `*_HOST_PORT` variables from `.env.example` to avoid port collisions.

Database and Redis volumes are isolated by Compose project.

**Security:** Host ports bind to loopback by default. Public access requires an explicitly configured and secured reverse proxy.

---

## 7. Rider Earnings & Payout Policy

All financial decisions are calculated and enforced using deterministic application rules.

### 7.1 Completed Trip Earnings

The base fare is ₹25.

An additional ₹6 per kilometer is applied for distances beyond 2 km.

```text
Trip Fare = [₹25 + ₹6 × max(distance_km - 2, 0)] × Surge Multiplier
```

The final fare is rounded **half-up per trip**.

### 7.2 Daily Incentives

Riders completing at least 12 eligible trips in a day earn a ₹150 incentive.

### 7.3 Cancellation Penalties

Each applicable rider cancellation incurs a ₹10 penalty.

### 7.4 Dispute Eligibility

Only trips within the latest seven days, evaluated in Indian Standard Time (IST), are eligible for payout disputes.

### 7.5 Automatic Payout Rules

| Policy | Limit |
|---|---|
| Maximum Automatic Payout | ₹200 per dispute |
| Automatic Payout Frequency | Once per rider per day |
| Dispute Eligibility Window | Last 7 IST days |
| Claims Above ₹200 | Ops approval required |
| Repeat Same-Day Claims | Ops approval required |

Claims that violate automatic payout limits are escalated rather than automatically paid.

See [Complete Payout Policy](docs/policy.md).

---

## 8. Payment Processing & Safety

QuickDrop AI distinguishes between payout eligibility, authorization, provider processing, and confirmed settlement.

### Payment Lifecycle

```text
Rider Raises Dispute
         |
         v
Verify Trusted Rider Identity
         |
         v
Fetch Authoritative Trip Records
         |
         v
Calculate Eligible Earnings
         |
         v
Validate Payout Policy
         |
         v
   Eligible for Auto-Pay?
         |
    +----+----+
    |         |
   Yes        No
    |         |
    v         v
Transactional  Ops Approval
Reservation    Required
    |         |
    +----+----+
         |
         v
Create Idempotent Payment Intent
         |
         v
Durable Payment Worker
         |
         v
Reconcile Provider State
         |
         v
PaySwift Sandbox
         |
         v
Confirm Settlement Outcome
         |
         v
Update Case & Notify Rider
```

### Reliability Mechanisms

**Transactional reservations:** Prevent conflicting payout authorizations from bypassing the policy.

**Idempotent payment intents:** Protect against duplicate financial actions when requests are retried.

**Provider reconciliation:** Checks payment-provider state before deciding whether another execution attempt is safe.

**Uncertain-outcome handling:** A timeout or provider error is not automatically treated as payment failure.

**Separate authorization and settlement:** An approved payout does not imply that PaySwift has successfully settled the payment.

> PaySwift is a sandbox provider. The project does not perform real bank transfers.

---

## 9. API Reference

### POST `/messages`

Processes a rider message using trusted identity, request timestamps, agent reasoning, and deterministic tools.

**Request:**

```json
{
  "message_id": "msg-001",
  "rider_id": "R003",
  "text": "Mera kal ka payment kam aaya hai",
  "received_at": "2026-11-13T10:30:00+05:30"
}
```

**Response:**

```json
{
  "reply": "..."
}
```

`received_at` must be an ISO 8601 timezone-aware timestamp.

For retries, reuse the exact original request payload, including the same `message_id`.

### GET `/trace/{rider_id}`

Returns an ordered trace of execution steps for the specified rider.

Example:

```http
GET /trace/R003
```

Useful for examining agent decisions, tool usage, and payout processing.

### GET `/ops/pending`

Returns pending approvals and escalated cases requiring operations review.

```http
GET /ops/pending
```

### GET `/health`

Health endpoint for verifying backend availability.

```http
GET /health
```

For complete API specifications, see [Submission & API Contracts](SUBMISSION.md).

---

## 10. Operations Console

The Ops Console provides a human-in-the-loop review workflow for cases that require manual judgment or authorization.

Supported actions include:

1. Reviewing pending approvals and escalations.
2. Approving or rejecting payout requests.
3. Taking ownership of an existing case.
4. Sending replies to riders.
5. Adding private notes for internal coordination.
6. Resolving cases after investigation.

Real-time case updates are distributed using **Redis Pub/Sub and SSE**.

This ensures that operations staff can remain informed of case activity without relying exclusively on manual page refreshes.

---

## 11. Local Development

For development outside the full Docker workflow, use:

**Backend API**

```bash
make backend
```

**Background Worker**

```bash
make workers
```

**Frontend**

```bash
make frontend
```

Ensure the required supporting services and environment configuration are available before starting the individual processes.

---

## 12. Evaluation Framework

QuickDrop AI includes an HTTP-based evaluator for validating payout decisions, provider outcomes, and rider-facing delivery.

**Important:** Evaluations create financial side effects in the sandbox. Always use a fresh, isolated deployment.

### Run the Full Evaluation

```bash
python evals/run.py http://localhost:8000
```

This is equivalent to using the default backend URL:

```bash
python evals/run.py
```

The evaluator communicates through public HTTP APIs and inspects the PaySwift ledger.

The default PaySwift URL is:

```text
http://localhost:8081
```

To override it:

```bash
python evals/run.py \
  --payswift-url http://localhost:8081
```

### Run an Individual Scenario

```bash
python evals/run.py --scenario N
```

Use a fresh sandbox deployment when isolating a scenario.

### Nonlocal Evaluation

Nonlocal destinations require explicit authorization:

```bash
python evals/run.py http://example-host:8000 --allow-nonlocal
```

**Never run evaluations against production systems or shared development financial data.**

### Evaluation Output

Results are written to:

```text
evals/results.json
```

The evaluator reports the following separately:

- Decision correctness.
- Payout authorization.
- Provider payment outcome.
- Initial rider reply delivery.

This separation prevents an authorization decision from being incorrectly reported as a successful provider payment.

---

## 13. Testing & Verified Results

The following results are from the documented remediation and evaluation runs.

### Automated Validation

| Validation | Result |
|---|---|
| Backend Tests | 494 passed, 1 skipped |
| Frontend Tests | 33 passed |
| Lint | Passed |
| Type Checking | Passed |
| Production Build | Passed |

### Isolated Amazon Nova Evaluation

| Metric | Result |
|---|---|
| Decision & Provider Outcome Scenarios | 24/24 passed |
| Automatic Payouts | 11 |
| Total Automatic Payout Amount | ₹664 |
| Ops-Approved Payouts | 1 |
| Ops-Approved Amount | ₹425 |
| Initial Webhook Reply Delivery | 28/30 requests |
| Final Delivery After Delayed Acknowledgments | 30/30 requests |

The original webhook delivery result corresponds to 22/24 scenarios completing all initial deliveries. Two remaining acknowledgments completed later.

### Full Docker Compose HTTP Evaluation

| Metric | Result |
|---|---|
| Decision Scenarios | 24/24 passed |
| Final Reply Delivery | 30/30 |
| Provider Verification | Failed for 3 scenarios |
| Unresolved Payments | 2 after PaySwift HTTP 503 responses |

**Interpretation:** Decision correctness and reply delivery were verified successfully in the full Compose run. However, payment-provider verification was not fully successful.

The project should not be described as having passed every end-to-end payment test.

Full results and evidence are available in the [Remediation Report](evals/reports/final-remediation/REMEDIATION_REPORT.md).

---

## 14. Historical Evaluation & Time Handling

The application distinguishes historical evaluator timestamps from real operational time.

- Evaluator-provided historical timestamps take precedence for the corresponding scenario.
- `APP_REFERENCE_TIME` is an optional development-only override for interactive demonstrations.
- Development reference time does not override audit timestamps.
- Authentication and worker clocks remain based on real time.
- The real-date daily payout authorization guard is not replaced by the demo reference time.

These restrictions help preserve the separation between demonstration behavior and operational financial controls.

---

## 15. Known Limitations

The project includes documented limitations that are important when interpreting evaluation results.

**1. Delayed outbound vendor replies**

No outbound transport is supplied for delivering delayed vendor replies after the original request lifecycle has ended.

**2. Provider failure recovery**

A full Compose evaluation encountered PaySwift HTTP 503 responses, leaving two payment outcomes unresolved and causing three scenarios to fail provider verification.

**3. Partial operational readiness**

The application has substantial automated test coverage and verified decision behavior, but the remaining delivery and payment-recovery limitations mean operational readiness is partial.

**4. Sandbox-only payment execution**

PaySwift simulates payment processing. Real banking integration, operational security requirements, and production settlement guarantees are outside the verified implementation.

See the [Full Remediation Report](evals/reports/final-remediation/REMEDIATION_REPORT.md).

---

## 16. AI Execution Evidence

Redacted records of authentic AI interactions are included for review.

[View AI Session Logs](ai-logs/README.md)

Original audit evidence is preserved separately.

These artifacts support inspection of actual model interactions, rather than relying only on synthetic examples or claimed agent behavior.

---

## 17. Security Considerations

The implementation includes several safety boundaries:

- The LLM is not trusted to authorize or execute financial transactions.
- Rider identity is established through trusted application context.
- Earnings and eligibility depend on authoritative records.
- Payment operations use deterministic policy enforcement.
- Payment intents are idempotent.
- Provider reconciliation precedes unsafe retries.
- Ops approval is required for policy-restricted claims.
- Secrets remain in server-side environment configuration.
- Environment files should never be committed.
- Server secrets must not use the `NEXT_PUBLIC_` prefix.
- Docker services bind exposed host ports to loopback by default.
- Persistent volumes are not automatically destroyed during startup.

For production use, additional security, observability, operational controls, and payment-provider integration would require separate validation.

---

## 18. CI & Deployment Scope

The project supports automated testing, linting, type checking, and production-build verification.

However:

- CI does not deploy the application.
- CI does not initiate real-money transfers.
- Payment evaluations must run in isolated sandbox environments.
- Public deployment requires explicitly configured infrastructure and security controls.

---

## 19. Project Documentation

| Document | Description |
|---|---|
| [Payout Policy](docs/policy.md) | Earnings formulas, eligibility rules, and payout limits |
| [Agent Design](backend/docs/agent.md) | LangGraph behavior and deterministic tool boundaries |
| [API Contracts](SUBMISSION.md) | Submission requirements and HTTP API specifications |
| [Docker Verification](docs/DOCKER_VERIFICATION.md) | Container setup and verification guidance |
| [Remediation Report](evals/reports/final-remediation/REMEDIATION_REPORT.md) | Testing evidence, remediation results, and remaining limitations |
| [AI Session Logs](ai-logs/README.md) | Redacted records of actual AI interactions |

---

## 20. Summary

QuickDrop AI demonstrates how agentic AI can be integrated into a financial support workflow without giving the language model direct control over money.

The system combines:

- **LangGraph and LLMs** for multilingual understanding and response generation.
- **Deterministic policy enforcement** for financial correctness.
- **PostgreSQL-backed transaction controls** for payout authorization.
- **Idempotency and provider reconciliation** for safer payment processing.
- **Durable background workers** for asynchronous payment execution.
- **Redis Pub/Sub and SSE** for real-time updates.
- **Human-in-the-loop operations** for disputed and high-value claims.
- **Docker Compose and HTTP evaluation** for reproducible integration testing.

The result is a sandbox-backed demonstration of AI-assisted rider support, payment dispute resolution, and controlled financial workflow orchestration.

**Project status:** Functionally implemented and extensively tested, with documented limitations in delayed outbound delivery and certain provider-failure recovery scenarios.
