# Starter Project 1: Bulk Order Processing

A FastAPI workflow that turns a customer's raw bulk-order email into a structured order result and a draft reply. Python controls validation, stock checks, and the final status. Azure OpenAI extracts and summarizes text; it never decides whether an order is Ready.

## Workflow

1. **Extract (Azure OpenAI):** Parse the email into a Pydantic model with customer, city, deadline, product names, and quantities.
2. **Validate (Python):** Check required values, positive whole-number quantities, deadline format, and the three-day lead time.
3. **Check stock (Python and PostgreSQL):** Match exact product names without case or repeated-space differences and read stock through a parameterized repository query. Stock is never changed.
4. **Draft reply (Azure OpenAI):** Write a concise reply from the computed result and customer name. The raw email is not sent to this call.

The endpoint is POST /orders. A Need info result takes priority over Partial, which takes priority over Ready.

## Technology

- Python, FastAPI, Pydantic, and pytest
- Azure OpenAI through the openai package's AzureOpenAI client
- PostgreSQL 16 with Docker Compose
- psycopg 3 for parameterized, read-only product and stock lookup

## Project structure

    starter-project-1/
    ├── app/
    │   ├── clients/azure_openai.py
    │   ├── models/orders.py
    │   ├── repositories/products.py
    │   ├── services/order_workflow.py
    │   ├── config.py
    │   ├── email_parser.py
    │   └── main.py
    ├── data/
    │   ├── answer_key.json
    │   ├── README.md
    │   ├── seed.sql
    │   └── emails/
    │       ├── labelled/   (10 scored cases)
    │       └── practice/   (5 unscored cases)
    ├── docs/
    │   ├── design-notes.md
    │   ├── Starter-project.drawio
    │   └── Starter-project.drawio.png
    ├── scripts/evaluate.py
    ├── tests/test_order_workflow.py
    ├── .env.example
    ├── compose.yaml
    └── requirements.txt

## Prerequisites

- Python 3.11 or later
- Docker Desktop with Docker Compose
- An Azure OpenAI resource, deployment name, API version, and key for end-to-end requests
- Git, if cloning the repository

## Clone and set up

    git clone <repository-url>
    cd starter-project-1

Create and activate a virtual environment:

    py -m venv .venv
    .\.venv\Scripts\Activate.ps1

On macOS or Linux, activate it with source .venv/bin/activate.

Install dependencies:

    python -m pip install -r requirements.txt

## Configure Azure OpenAI and PostgreSQL

Copy the example file:

    Copy-Item .env.example .env

Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_VERSION, and AZURE_OPENAI_API_KEY. Set POSTGRES_PASSWORD and make the password in DATABASE_URL match it. The example values are placeholders; the service will not connect until replaced.

## Start PostgreSQL

    docker compose up -d postgres

Compose reads the POSTGRES_DB, POSTGRES_USER, and POSTGRES_PASSWORD variables from .env. It mounts data/seed.sql into the official image's initialization directory and keeps database files in a persistent volume. The seed script runs only when that volume is first initialized.

Verify both tables contain 15 rows:

    docker compose exec postgres psql -U starter -d starter_project_1 -c "SELECT 'products' AS table_name, count(*) FROM products UNION ALL SELECT 'stock', count(*) FROM stock;"

If you changed the database name or user, use those values instead. If reusing an old volume prevents initialization, inspect your data before removing any volume; removing it deletes the local database contents.

## Start the API

    python -m uvicorn app.main:app --reload --env-file .env

Swagger UI: http://127.0.0.1:8000/docs
OpenAPI JSON: http://127.0.0.1:8000/openapi.json

Send a sample request from PowerShell:

    $email = @'
    From: buyer@example.com
    Date: Tue, 17 Nov 2026 09:00:00 +0000
    Subject: Bulk order

    Greenfield Public School in Nagpur needs 10 Nimbus Tab 10 by 30 November 2026.
    '@
    $body = @{ email = $email } | ConvertTo-Json
    Invoke-RestMethod -Uri http://127.0.0.1:8000/orders -Method Post -ContentType "application/json" -Body $body

The response includes customer, delivery_city, deadline, items, status, issues, and reply. Every key is returned, including keys whose values are null.

## Run tests

    python -m pytest

The tests exercise validation, status priority, product matching, unknown items, previous-order references, and stock comparison without connecting to PostgreSQL or Azure OpenAI.

## Run evaluation

Start PostgreSQL and the API, then run:

    python scripts/evaluate.py

The evaluator sends all 10 labelled messages to the live endpoint and scores five fields per email: exact status, item (product_code, requested) pairs independent of order, customer and city ignoring case and outer spaces, and exact deadline including null. It reports misses and a total out of 50. The five practice messages are then run and printed without contributing to the score. Set STARTER_PROJECT_API_URL to use a different API URL.

Evaluation depends on working Azure credentials and a running, seeded database. Results can change when extraction differs; the evaluator reports observed mismatches and does not claim a score until it has actually completed.

## Common errors and troubleshooting

- Azure configuration error: check that all four Azure settings are present in .env and that the deployment name is correct.
- Azure timeout or rate limit: the client retries timeouts, connection errors, and HTTP 429 responses up to the configured attempt limit. Retry later if the final request fails.
- PostgreSQL connection error: check docker compose ps, database credentials, and DATABASE_URL. If port 5432 is occupied, set POSTGRES_PORT=5433 in .env and use port 5433 in DATABASE_URL.
- Tables are missing: Postgres only runs initialization scripts on an empty data volume. Check the seed mount path and whether Compose is reusing an older volume.
- Evaluation cannot connect: confirm the API URL, database, and Azure settings.

## Security

Keep .env local and never commit it. It contains credentials. .env.example is safe to share because its values are placeholders. API responses use generic configuration, database, and internal-error messages; application logs should not contain the Azure key.

