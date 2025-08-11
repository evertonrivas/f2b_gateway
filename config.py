from typing import Dict, List

# Serviço -> lista de instâncias (url base)
SERVICES: Dict[str, List[str]] = {
    "users": ["http://localhost:5001", "http://localhost:5003"],
    "orders": ["http://localhost:5002"]
}

# JWT settings
JWT_ISSUER = "my-auth-server"
JWT_AUDIENCE = "api-gateway"
JWT_PUBLIC_KEY = """
-----BEGIN PUBLIC KEY-----
...COLE AQUI A CHAVE PÚBLICA RSA (ou use HS secret)
-----END PUBLIC KEY-----
"""
# or for HS:
# JWT_SECRET = "supersecret"

# Timeouts/retries
HTTP_TIMEOUT = 5.0  # segundos
RETRIES = 2  # número de retries em falhas transitórias
BACKOFF_FACTOR = 0.3

# Circuit breaker
CB_FAIL_MAX = 5
CB_RESET_TIMEOUT = 30  # segundos

# Rate limit
RATE_LIMIT_STR = "100 per minute; 20 per second"  # default global

# Healthcheck interval / timeouts
HEALTHCHECK_TIMEOUT = 2.0
