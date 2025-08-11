# requirements: Flask, PyJWT, requests, SQLAlchemy, psycopg2-binary
from flask import Flask, request, jsonify, g
import jwt
import requests
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from config import SECRET, DB_URL, SERVICE_MAP

app = Flask(__name__)

# Único engine (recomendado) e factory de sessions
engine = create_engine(DB_URL, pool_size=20, max_overflow=40)
SessionLocal = sessionmaker(bind=engine)

# --- Middleware: decodifica JWT e extrai tenant ---
@app.before_request
def extract_tenant_from_jwt():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "missing token"}), 401
    token = auth.split(None, 1)[1]
    try:
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])  # ou RS256 com chave pública
    except jwt.ExpiredSignatureError:
        return jsonify({"error": "token expired"}), 401
    except jwt.InvalidTokenError:
        return jsonify({"error": "invalid token"}), 401

    # espera que o JWT contenha "profile" com o schema/tenant id
    tenant = payload.get("profile")
    if not tenant:
        return jsonify({"error": "tenant (profile) missing in token"}), 403

    # opcional: validar se tenant existe (cache)
    # ex.: if not tenant_in_allowlist(tenant): return 404/403
    g.tenant = tenant
    g.jwt_payload = payload

# --- Helper: criar sessão DB e setar search_path ---
def get_db_session_for_tenant(tenant):
    session = SessionLocal()
    # setar search_path para Postgres
    session.execute(text(f"SET search_path TO {tenant}"))
    return session

# --- Proxy simples para microservices ---
@app.route("/api/<service>/<path:subpath>", methods=["GET","POST","PUT","PATCH","DELETE"])
def proxy(service, subpath):
    if service not in SERVICE_MAP:
        return jsonify({"error": "unknown service"}), 404

    target = f"{SERVICE_MAP[service]}/{subpath}"
    # repassa headers essenciais (incluir tenant para os microservices)
    headers = {k: v for k, v in request.headers if k.lower() != "host"}
    headers["X-Tenant-Schema"] = g.tenant
    # manter o Authorization caso microservices precisem validar
    resp = requests.request(
        method=request.method,
        url=target,
        headers=headers,
        params=request.args,
        data=request.get_data(),
        timeout=10
    )
    return (resp.content, resp.status_code, resp.headers.items())

# --- Endpoint que usa DB (exemplo) ---
@app.route("/api/internal/report", methods=["GET"])
def report():
    tenant = g.tenant
    session = get_db_session_for_tenant(tenant)
    try:
        # exemplo: consulta em schema atual
        r = session.execute(text("SELECT count(*) FROM users")).scalar()
        return jsonify({"tenant": tenant, "users_count": int(r)})
    finally:
        session.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
