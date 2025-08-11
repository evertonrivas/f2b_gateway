import itertools
import logging
import time
from typing import Dict, List

from flask import Flask, request, jsonify, Response, g
import httpx
import jwt
from jwt import InvalidTokenError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import pybreaker
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

from config import SERVICES, JWT_PUBLIC_KEY, JWT_ISSUER, JWT_AUDIENCE, HTTP_TIMEOUT, RETRIES, BACKOFF_FACTOR, CB_FAIL_MAX, CB_RESET_TIMEOUT, RATE_LIMIT_STR, HEALTHCHECK_TIMEOUT

app = Flask(__name__)

# logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("api-gateway")

# Rate limiter
limiter = Limiter(app=app, key_func=get_remote_address, default_limits=[RATE_LIMIT_STR])

# Prometheus metrics
REQUEST_COUNT = Counter("gateway_requests_total", "Total requests proxied", ["service", "method", "status"])

# Create round-robin iterators for each service
_service_iters: Dict[str, itertools.cycle] = {}
for svc, instances in SERVICES.items():
    _service_iters[svc] = itertools.cycle(instances)

# Circuit breakers per service
_circuit_breakers = {
    svc: pybreaker.CircuitBreaker(fail_max=CB_FAIL_MAX, reset_timeout=CB_RESET_TIMEOUT, name=f"cb-{svc}")
    for svc in SERVICES.keys()
}

# httpx client with connection pooling
# We'll create a client per request or reuse a global client; httpx client is thread-safe for sync usage.
client = httpx.Client(timeout=HTTP_TIMEOUT)

# Helper: choose next instance (round robin)
def choose_instance(service_name: str) -> str:
    try:
        return next(_service_iters[service_name])
    except KeyError:
        raise ValueError(f"Service {service_name} not configured")

# Helper: verify JWT
def verify_jwt_from_header():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise InvalidTokenError("Missing Bearer token")
    token = auth.split(" ", 1)[1].strip()
    # verify signature and claims
    payload = jwt.decode(token, JWT_PUBLIC_KEY, algorithms=["RS256"], audience=JWT_AUDIENCE, issuer=JWT_ISSUER)
    return payload

# Helper: forward request to upstream with retries and circuit breaker
def forward_request(service: str, path: str):
    breaker = _circuit_breakers.get(service)
    if breaker is None:
        # treat as unknown service
        return Response("Unknown service", status=502)

    @breaker
    def call_upstream(instance_url: str):
        url = instance_url.rstrip("/") + "/" + path.lstrip("/")
        # build headers (remove hop-by-hop)
        headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length", "transfer-encoding", "connection", "keep-alive"]}
        # inject user claims (optionally)
        # headers['X-User-Id'] = user_id
        # retries simple loop
        last_exc = None
        for attempt in range(RETRIES + 1):
            try:
                resp = client.request(
                    method=request.method,
                    url=url,
                    headers=headers,
                    params=request.args,
                    content=request.get_data(),
                    cookies=request.cookies,
                    allow_redirects=False,
                    timeout=HTTP_TIMEOUT
                )
                return resp
            except (httpx.TransportError, httpx.ReadTimeout) as e:
                last_exc = e
                backoff = BACKOFF_FACTOR * (2 ** attempt)
                logger.warning("Upstream attempt %s failed for %s: %s. Backing off %.2fs", attempt, url, e, backoff)
                time.sleep(backoff)
        # if reached here, raise last exception to trip circuit breaker
        raise last_exc

    # choose instance and call
    for attempt in range(len(SERVICES.get(service, []))):
        instance = choose_instance(service)
        try:
            resp = call_upstream(instance)
        except pybreaker.CircuitBreakerError as cb_err:
            logger.warning("Circuit open for service %s: %s", service, cb_err)
            return Response("Upstream circuit open", status=503)
        except Exception as e:
            logger.exception("Call to %s failed on instance %s: %s", service, instance, e)
            # try next instance
            continue
        # success
        return Response(resp.content, status=resp.status_code, headers=dict(resp.headers))
    # all instances failed
    return Response("All upstream instances failed", status=502)

# Middleware: authenticate (example, can be optional per route)
@app.before_request
def authenticate():
    # skip health and metrics
    if request.path.startswith("/health") or request.path.startswith("/metrics"):
        return None
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return jsonify({"error": "missing authorization"}), 401
    try:
        payload = verify_jwt_from_header()
        # Attach claims to "g" for handlers to use
        g.jwt = payload
    except InvalidTokenError as e:
        logger.warning("Invalid token: %s", e)
        return jsonify({"error": "invalid_token", "msg": str(e)}), 401
    except Exception as e:
        logger.exception("JWT verification error: %s", e)
        return jsonify({"error": "jwt_error"}), 401

# Generic proxy endpoint (catch-all per service)
@app.route("/<service>/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@limiter.limit("50 per minute")  # example per-route limit (you can make it dynamic per key)
def proxy(service, path):
    if service not in SERVICES:
        return jsonify({"error": "service_not_found"}), 404
    resp = forward_request(service, path)
    try:
        REQUEST_COUNT.labels(service=service, method=request.method, status=str(resp.status_code)).inc()
    except Exception:
        pass
    return resp

# Health endpoint
@app.route("/health")
def health():
    # simple gateway health + optional upstream quick checks
    results = {"gateway": "ok", "upstreams": {}}
    for svc, instances in SERVICES.items():
        ok_count = 0
        instance_status = {}
        for inst in instances:
            try:
                r = client.get(f"{inst.rstrip('/')}/health", timeout=HEALTHCHECK_TIMEOUT)
                instance_status[inst] = {"status_code": r.status_code}
                if 200 <= r.status_code < 300:
                    ok_count += 1
            except Exception as e:
                instance_status[inst] = {"error": str(e)}
        results["upstreams"][svc] = {"healthy_instances": ok_count, "instances": instance_status}
    return jsonify(results)

# Prometheus metrics endpoint
@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

# root
@app.route("/")
def index():
    return jsonify({"message": "API Gateway running"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
