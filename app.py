from flask import Flask, request, jsonify
import requests
from config import SERVICES

app = Flask(__name__)

# Exemplo: rota para repassar requisições ao microsserviço de usuários
@app.route("/users/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def users_proxy(path):
    url = f"{SERVICES['users']}/{path}"
    resp = requests.request(
        method=request.method,
        url=url,
        headers={key: value for key, value in request.headers if key != "Host"},
        params=request.args,
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False
    )
    return (resp.content, resp.status_code, resp.headers.items())


# Rota para repassar requisições ao microsserviço de pedidos
@app.route("/orders/<path:path>", methods=["GET", "POST", "PUT", "DELETE"])
def orders_proxy(path):
    url = f"{SERVICES['orders']}/{path}"
    resp = requests.request(
        method=request.method,
        url=url,
        headers={key: value for key, value in request.headers if key != "Host"},
        params=request.args,
        data=request.get_data(),
        cookies=request.cookies,
        allow_redirects=False
    )
    return (resp.content, resp.status_code, resp.headers.items())


@app.route("/")
def health():
    return jsonify({"status": "API Gateway running"})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
