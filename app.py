from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
import jwt  # PyJWT
from config import SERVICES_URL, SECRET_JWT

app = FastAPI()

def get_profile_from_jwt(token: str) -> str:
    try:
        payload = jwt.decode(token, SECRET_JWT, algorithms=["HS256"])
        return payload.get("profile")
    except Exception:
        raise HTTPException(status_code=401, detail="Token inválido")


@app.api_route("/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def gateway(service: str, path: str, request: Request):
    # Verifica se o serviço existe
    if service not in SERVICE_URLS:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")

    # Extrair o token JWT do header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token não fornecido")

    token = auth_header.split(" ")[1]

    # Extrair profile do JWT
    profile = get_profile_from_jwt(token)
    if not profile:
        raise HTTPException(status_code=401, detail="Profile não encontrado no token")

    # Montar URL do microserviço
    url = f"{SERVICE_URLS[service]}/{path}"

    # Preparar dados para encaminhar
    client = httpx.AsyncClient()

    # Copiar método, headers, query params e body da requisição original
    method = request.method
    headers = dict(request.headers)
    # Remover headers que podem causar problemas (host, etc)
    headers.pop("host", None)
    # Adicionar header customizado com profile (se quiser)
    headers["X-Tenant-Profile"] = profile

    query_params = dict(request.query_params)
    body = await request.body()

    # Fazer requisição para o macroserviço
    try:
        resp = await client.request(method, url, headers=headers, params=query_params, content=body)
        return JSONResponse(status_code=resp.status_code, content=resp.json())
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Erro ao conectar com o serviço: {e}")
    finally:
        await client.aclose()
