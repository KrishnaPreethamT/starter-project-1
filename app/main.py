import logging
from functools import lru_cache

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.clients.azure_openai import AzureLLMClient, LLMServiceError
from app.config import Settings
from app.email_parser import EmailInputError, parse_email
from app.models.orders import OrderRequest
from app.repositories.products import ProductRepository
from app.services.order_workflow import OrderWorkflow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)
app = FastAPI(title="Starter Project 1", version="1.0.0")


@app.exception_handler(RequestValidationError)
async def invalid_request_body(_: Request, exc: RequestValidationError):
    logger.info("Request validation failed: %d issue(s)", len(exc.errors()))
    return JSONResponse(status_code=422, content={"detail": "Invalid request body"})


@lru_cache
def get_settings() -> Settings:
    return Settings.from_environment()


def get_workflow() -> OrderWorkflow:
    settings = get_settings()
    return OrderWorkflow(AzureLLMClient(settings), ProductRepository(settings.database_url), settings)


@app.post("/orders")
def process_order(request: OrderRequest):
    logger.info("POST /orders received")
    try:
        parsed_email = parse_email(request.email)
        logger.info("Email parsed: date_header_present=%s", bool(parsed_email.sent_at))
        return get_workflow().process(parsed_email).model_dump()
    except EmailInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        logger.error("Configuration error: %s", exc)
        raise HTTPException(status_code=503, detail="Order processing is not configured") from exc
    except LLMServiceError as exc:
        logger.error("LLM service failure: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except psycopg.Error as exc:
        logger.exception("Database operation failed")
        raise HTTPException(status_code=503, detail="Product stock service is unavailable") from exc
    except Exception as exc:
        logger.exception("Unexpected order processing error")
        raise HTTPException(status_code=500, detail="Order processing failed") from exc
