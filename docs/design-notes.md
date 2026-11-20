# Starter Project 1 – Architecture Design Notes

## Project Overview
The project is designed to automate bulk order processing for a fictional electronics distributor. It receives customer order emails, extracts order details, validates the information, checks product availability and generates a customer reply.

## Workflow Architecture

1. Extract: Azure OpenAI extracts customer name, delivery city, deadline, product names and quantities into a structured Pydantic model.
2. Validate: Python validates required fields, quantities and deadline requirements.
3. Check Stock: A repository class queries PostgreSQL to retrieve product information and available stock.
4. Status Decision: Python determines whether the order is Ready, Partial or Need info.
5. Draft Reply: Azure OpenAI generates a customer response using the computed order results.

## Technology Components

- FastAPI: Exposes the POST /orders endpoint.
- Azure OpenAI: Handles order extraction and customer reply generation.
- Pydantic: Defines structured order data.
- PostgreSQL: Stores product and stock information.
- Repository Pattern: Handles parameterised SQL queries.
- Configuration: Stores application settings and credentials in environment variables.
- Error Handling: Handles exceptions, API failures, timeouts and retries.
- Logging: Records workflow execution, token usage and LLM latency.

## Database Design

The database contains two tables:

- products: product_code, name, category and unit_price_inr.
- stock: product_code and quantity_available.

The tables are joined using product_code. Stock information is read-only.

## Business Rules

- Ready: All details are valid and sufficient stock is available.
- Partial: The order is valid, but stock is insufficient for one or more items.
- Need info: Required information is missing or invalid, the product is unknown, or the deadline is unacceptable.

Python determines the final order status. The LLM is responsible only for extraction and reply generation.

## Expected API Response

POST /orders returns customer, delivery_city, deadline, items, status, issues and reply.