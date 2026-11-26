from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class ProductStock:
    product_code: str
    product_name: str
    available: int
    unit_price_inr: Decimal = Decimal("0")


@dataclass(frozen=True)
class HistoricalItem:
    product_code: str
    product_name: str
    quantity: int


class ProductRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def find_product(self, product_name: str) -> ProductStock | None:
        import psycopg

        normalized_name = " ".join(product_name.split()).casefold()
        predicates = ["lower(regexp_replace(btrim(p.name), '\\s+', ' ', 'g')) = %s"]
        params: list[str] = [normalized_name]
        # Accept only a canonical catalogue name followed by its generic
        # category noun. These are controlled aliases, not fuzzy matching.
        category_suffixes = (
            ("laptop", r"\s+laptops?$"),
            ("smartphone", r"\s+(?:phones?|smartphones?)$"),
        )
        import re
        for category, suffix in category_suffixes:
            base_name = re.sub(suffix, "", normalized_name, flags=re.IGNORECASE)
            if base_name != normalized_name:
                predicates.append(
                    "(lower(p.category) = %s AND "
                    "lower(regexp_replace(btrim(p.name), '\\s+', ' ', 'g')) = %s)"
                )
                params.extend((category, base_name))
        query = f"""
            SELECT p.product_code, p.name, s.quantity_available, p.unit_price_inr
            FROM products AS p
            JOIN stock AS s ON s.product_code = p.product_code
            WHERE {' OR '.join(predicates)}
        """
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        if len(rows) != 1:
            return None
        row = rows[0]
        return ProductStock(product_code=row[0], product_name=row[1], available=row[2], unit_price_inr=Decimal(str(row[3])))

    def find_product_by_code(self, product_code: str) -> ProductStock | None:
        import psycopg
        query = """SELECT p.product_code, p.name, s.quantity_available, p.unit_price_inr
                   FROM products p JOIN stock s USING (product_code) WHERE p.product_code = %s"""
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            row = connection.execute(query, (product_code,)).fetchone()
        return ProductStock(row[0], row[1], row[2], Decimal(str(row[3]))) if row else None

    def latest_order(self, customer: str) -> list[HistoricalItem]:
        import psycopg
        query = """WITH latest_order AS (
                       SELECT order_id FROM order_history
                       WHERE lower(btrim(customer)) = lower(btrim(%s))
                       ORDER BY order_date DESC, order_id DESC
                       LIMIT 1
                   )
                   SELECT h.product_code, p.name, h.quantity FROM order_history h
                   JOIN latest_order latest USING (order_id)
                   JOIN products p USING (product_code)
                   WHERE lower(btrim(h.customer)) = lower(btrim(%s))
                   ORDER BY h.product_code"""
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            rows = connection.execute(query, (customer, customer)).fetchall()
        return [HistoricalItem(row[0], row[1], row[2]) for row in rows]
