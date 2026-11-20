from dataclasses import dataclass

@dataclass(frozen=True)
class ProductStock:
    product_code: str
    product_name: str
    available: int


class ProductRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def find_product(self, product_name: str) -> ProductStock | None:
        import psycopg

        normalized_name = " ".join(product_name.split()).casefold()
        query = """
            SELECT p.product_code, p.name, s.quantity_available
            FROM products AS p
            JOIN stock AS s ON s.product_code = p.product_code
            WHERE lower(regexp_replace(btrim(p.name), '\\s+', ' ', 'g')) = %s
        """
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            row = connection.execute(query, (normalized_name,)).fetchone()
        if row is None:
            return None
        return ProductStock(product_code=row[0], product_name=row[1], available=row[2])
