# Starter Project 2: RAG-Enhanced Order Desk

A FastAPI workflow that turns a customer's raw bulk-order email into a structured order result and a draft reply. Python controls validation, stock checks, and the final status. Azure OpenAI extracts and summarizes text; it never decides whether an order is Ready.

## Workflow

1. **Extract (Azure OpenAI):** Parse the email into a Pydantic model with customer, city, deadline, product names/descriptions, quantities, and repeat-order intent.
2. **Retrieve (Azure OpenAI and pgvector):** Embed product descriptions and retrieve relevant brochure or policy chunks. Python limits resolution to products in the retrieved catalogue candidates.
3. **Validate and calculate (Python):** Check required fields and deadlines, resolve repeat orders from history, check stock, determine status, and calculate quotes with Decimal values.
4. **Draft reply (Azure OpenAI):** Write from the computed result and retrieved reference context. The raw email is not sent to this call.

The `/orders` endpoint supports product-description lookup using brochure chunks in pgvector, repeats a customer's latest order from history, and adds a calculated quote. A Need info result takes priority over Partial, which takes priority over Ready. Starter Project 1 behavior and data remain supported.

## Technology

- Python, FastAPI, Pydantic, and pytest
- Azure OpenAI through the openai package's AzureOpenAI client
- PostgreSQL 16 with pgvector through Docker Compose
- psycopg 3 for parameterized, read-only product and stock lookup

## Project structure

    starter-project-1/
    ├── app/
    │   ├── clients/azure_openai.py
    │   ├── models/orders.py
    │   ├── repositories/products.py
    │   ├── repositories/documents.py
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
    ├── scripts/evaluate_starter_project_2.py
    ├── scripts/ingest_documents.py
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

Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_DEPLOYMENT, AZURE_OPENAI_API_VERSION, AZURE_OPENAI_API_KEY, and AZURE_OPENAI_EMBEDDING_DEPLOYMENT. Set POSTGRES_PASSWORD and make the password in DATABASE_URL match it. The example values are placeholders; the service will not connect until replaced.

## Start PostgreSQL

    docker compose up -d postgres

Compose reads the POSTGRES_DB, POSTGRES_USER, and POSTGRES_PASSWORD variables from .env. It uses `pgvector/pgvector:pg16`, keeps database files in a persistent volume, and runs the S1 and S2 seed scripts in order only when that volume is first initialized. Existing volumes are preserved; do not use `docker compose down -v` if you need the current database. Apply the additive S2 seed to an existing volume with `Get-Content .\data\starter-project-2\sp2_seed.sql -Raw | docker compose exec -T postgres psql -U starter -d starter_project_1` (adjust the user/database if your environment uses different values).

After the database and Azure embedding deployment are ready, run the idempotent document ingest:

    python scripts/ingest_documents.py

It reads markdown under `data/starter-project-2/docs`, chunks by heading, and upserts vectors by source and heading. Re-running it refreshes rather than duplicates chunks.

Verify products and stock have 15 rows each, order_history has 9, and vector is enabled:

    docker compose exec postgres psql -U starter -d starter_project_1 -c "SELECT 'products' AS table_name, count(*) FROM products UNION ALL SELECT 'stock', count(*) FROM stock;"

    docker compose exec postgres psql -U starter -d starter_project_1 -c "SELECT count(*) FROM order_history; SELECT extname FROM pg_extension WHERE extname = 'vector';"

If you changed the database name or user, use those values instead. With an existing volume, use the additive seed command above; it keeps existing S1 rows and does not remove the volume.

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

The response includes customer, delivery_city, deadline, items, status, issues, reply, and quote. Every key is returned, including keys whose values are null.

## Run tests

    python -m pytest

The tests exercise validation, status priority, product matching, RAG candidate resolution, repeat-order behavior, quote calculation, and stock comparison without connecting to PostgreSQL or Azure OpenAI.

## Run evaluation

Start PostgreSQL and the API, then run the Starter Project 1 regression evaluator:

    python scripts/evaluate.py

That evaluator sends the original 10 labelled messages. To score Starter Project 2's cases, run `python scripts/evaluate_starter_project_2.py`; it checks the contract fields and quote values against the supplied key, then prints five practice cases without scoring them. Set STARTER_PROJECT_API_URL to use a different API URL.

Evaluation depends on working Azure credentials and a running, seeded database. Results can change when extraction differs; the evaluator reports observed mismatches and does not claim a score until it has actually completed.

## Common errors and troubleshooting

- Azure configuration error: check that all five Azure settings are present in .env and that the deployment names are correct.
- Azure timeout or rate limit: the client retries timeouts, connection errors, and HTTP 429 responses up to the configured attempt limit. Retry later if the final request fails.
- PostgreSQL connection error: check docker compose ps, database credentials, and DATABASE_URL. If port 5432 is occupied, set POSTGRES_PORT=5433 in .env and use port 5433 in DATABASE_URL.
- Tables are missing: Postgres only runs initialization scripts on an empty data volume. Check the seed mount path and whether Compose is reusing an older volume.
- Evaluation cannot connect: confirm the API URL, database, and Azure settings.

## Security

Keep .env local and never commit it. It contains credentials. .env.example is safe to share because its values are placeholders. API responses use generic configuration, database, and internal-error messages; application logs should not contain the Azure key.

