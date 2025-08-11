import os

# Mapear prefixo -> url do microserviço

SERVICE_URLS = {
    "cmm": "http://localhost:8001/cmm/api",
    "b2b": "http://localhost:8002/b2b/api",
    "crm": "http://localhost:8003/crm/api",
    "scm": "http://localhost:8004/scm/api"
}

SECRET_JWT = "sua_chave_secreta"  # para validar o JWT, se tiver
