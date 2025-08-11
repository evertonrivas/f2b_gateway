import os

SECRET = "seu-segredo-ou-chave-publica"

DB_URL = "postgresql://user:pass@db-host:5432/dbname"

SERVICE_MAP = {
    # rota inicial -> service URL base
    "users": "http://users-service.internal",
    "orders": "http://orders-service.internal",
}
