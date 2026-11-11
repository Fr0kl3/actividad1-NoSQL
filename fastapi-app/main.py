from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
from pymongo import MongoClient
from bson import ObjectId
from bson.errors import InvalidId
import os, requests

app = FastAPI(title="API NoSQL (vulnerable)")
mongo = MongoClient(os.getenv("MONGO_HOST","mongo"), 27017)
db = mongo[os.getenv("MONGO_DATABASE","tienda")]

class Login(BaseModel): username: str; password: str
class Pedido(BaseModel): producto: str; cantidad: int

@app.post("/login_mongo")
async def login(req: Request):
    data = await req.json()
    # ❌ NoSQLi: acepta operadores $ en credenciales
    user = db.usuarios.find_one({"username": data.get("username"),
                                 "password": data.get("password")}, {"_id":0})
    if user: return {"msg":"ok"}
    raise HTTPException(status_code=401, detail="Bad creds")

@app.get("/articulos")
def art_search(q: str="*"):
    return requests.get("http://elasticsearch:9200/articulos/_search",
                        params={"q": q}).json()

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
