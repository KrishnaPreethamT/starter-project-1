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
        query = """
            SELECT p.product_code, p.name, s.quantity_available, p.unit_price_inr
            FROM products AS p
            JOIN stock AS s ON s.product_code = p.product_code
            WHERE lower(regexp_replace(btrim(p.name), '\\s+', ' ', 'g')) = %s
        """
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            row = connection.execute(query, (normalized_name,)).fetchone()
        if row is None:
            return None
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
        query = """WITH latest AS (
                       SELECT max(order_date) AS order_date FROM order_history
                   WHERE lower(btrim(customer)) = lower(btrim(%s))
                   )
                   SELECT h.product_code, p.name, h.quantity FROM order_history h
                   JOIN latest l USING (order_date) JOIN products p USING (product_code)
                   WHERE lower(btrim(h.customer)) = lower(btrim(%s)) ORDER BY h.product_code"""
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            rows = connection.execute(query, (customer, customer)).fetchall()
        return [HistoricalItem(row[0], row[1], row[2]) for row in rows]
