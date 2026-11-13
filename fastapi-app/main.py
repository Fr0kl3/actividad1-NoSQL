from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from pymongo import MongoClient
from bson import ObjectId
from bson.errors import InvalidId
from collections import defaultdict, deque
import os, requests, logging, re, time

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("api")
app = FastAPI(title="API NoSQL (Defensa Ampliada)")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
mongo = MongoClient(os.getenv("MONGO_HOST","mongo"),
    port = 27017,
    username=os.getenv("MONGO_USER"),
    password=os.getenv("MONGO_PASS"),
    authSource="tienda",
    tls=True,
    tlsCAFile="/mongo-certs/ca.crt")
db = mongo[os.getenv("MONGO_DATABASE","tienda")]
#rate limit
@app.exception_handler(RateLimitExceeded)
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    log.warning("rate limit ip=%s ruta=%s", get_remote_address(request), request.url.path)
    return JSONResponse(status_code=429, content={"detail": "Demasiadas peticiones"})

#umbrales
ventanas = defaultdict(deque)
def registrar(tipo, clave, umbral, segundos=60):
    ahora = time.time()
    d = ventanas[(tipo, clave)]
    d.append(ahora)
    while d and d[0] < ahora - segundos:
        d.popleft()
    if len(d) == umbral:
        log.error("ALERTA tipo=%s origen=%s eventos=%d en %ds",
                  tipo, clave, len(d), segundos)


class Login(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username", "password")
    @classmethod
    def sin_operadores(cls, v):
        if "$" in v:
            raise ValueError("caracter '$' no permitido")
        return v


class Pedido(BaseModel): producto: str; cantidad: int

@app.post("/login_mongo")
@limiter.limit("5/minute")
def login(request: Request, data: Login):
    user = db.usuarios.find_one(
        {"username": data.username, "password": data.password},
        {"_id": 0})
    if user:
        return {"msg": "ok"}
    log.warning("login fallido user=%s", data.username)
    registrar("login_fallido", get_remote_address(request), 3)
    raise HTTPException(status_code=401, detail="Bad creds")

@app.get("/articulos")
@limiter.limit("30/minute")
def art_search(
    request: Request,
    q: str = Query(min_length=1, max_length=100),
    page: int = Query(1, ge=1, le=100),
    size: int = Query(10, ge=1, le=50),
):
    registrar("pico_busqueda", get_remote_address(request), 20)
    q_limpia = re.sub(r'([+\-=&|><!(){}\[\]^"~*?:\\/])', r'\\\1', q)
    body = {
        "from": (page - 1) * size,
        "size": size,
        "query": {"match": {"titulo": q_limpia}},
    }
    r = requests.post(
        "https://elasticsearch:9200/articulos/_search",
        json=body,
        auth=("elastic", os.getenv("ELASTIC_PASS")),
        verify="/mongo-certs/ca.crt",
        timeout=10,
    )
    if r.status_code != 200:
        log.warning("error ES status=%s q=%r", r.status_code, q)
        raise HTTPException(502, "Error de búsqueda")
    hits = r.json()["hits"]
    return {"total": hits["total"]["value"], "page": page,
            "items": [h["_source"] for h in hits["hits"]]}

# parametros para  api pedidos 


def _id_valido(pedido_id: str) -> ObjectId:
    try:
        return ObjectId(pedido_id)
    except InvalidId:
        raise HTTPException(status_code=422, detail="ID invalido")

@app.post("/pedidos", status_code=201)
def crear_pedido(p: Pedido):
    res = db.pedidos.insert_one(p.model_dump())
    return {"id": str(res.inserted_id)}

@app.get("/pedidos")
def listar_pedidos():
    return [{"id": str(d["_id"]), "producto": d["producto"], "cantidad": d["cantidad"]}
            for d in db.pedidos.find()]

@app.put("/pedidos/{pedido_id}")
def actualizar_pedido(pedido_id: str, p: Pedido):
    res = db.pedidos.update_one({"_id": _id_valido(pedido_id)},
                                {"$set": p.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return {"msg": "actualizado"}

@app.delete("/pedidos/{pedido_id}")
def borrar_pedido(pedido_id: str):
    res = db.pedidos.delete_one({"_id": _id_valido(pedido_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    return {"msg": "eliminado"}
