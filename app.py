"""
app.py - Northwind renovado: Flask + MongoDB
Panel, clientes, productos y pedidos con operaciones básicas (CRUD).
"""
import os
import re
from datetime import date

from flask import Flask, flash, redirect, render_template, request, url_for
from pymongo import MongoClient, DESCENDING

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "northwind-demo")

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
db = MongoClient(MONGO_URI)[os.environ.get("MONGO_DB", "northwind")]

POR_PAGINA = 15


# ---------------------------------------------------------------- utilidades
@app.template_filter("dinero")
def dinero(valor):
    return f"${valor or 0:,.2f}"


def buscar(texto, campos):
    """Arma un filtro de búsqueda (sin distinguir mayúsculas) sobre varios campos."""
    if not texto:
        return {}
    patron = re.escape(texto)
    return {"$or": [{c: {"$regex": patron, "$options": "i"}} for c in campos]}


def paginar(coleccion, filtro, orden, pagina):
    total = coleccion.count_documents(filtro)
    paginas = max(1, -(-total // POR_PAGINA))
    pagina = min(max(pagina, 1), paginas)
    docs = list(coleccion.find(filtro).sort(orden).skip((pagina - 1) * POR_PAGINA).limit(POR_PAGINA))
    return docs, {"pagina": pagina, "paginas": paginas, "total": total}


def siguiente_id(coleccion):
    ultimo = coleccion.find_one(sort=[("_id", DESCENDING)])
    return (ultimo["_id"] + 1) if ultimo else 1


def numero(texto, tipo=float, defecto=0):
    try:
        return tipo(texto)
    except (TypeError, ValueError):
        return defecto


# ---------------------------------------------------------------------- panel
@app.route("/")
def panel():
    ventas = list(db.pedidos.aggregate([{"$group": {"_id": None, "t": {"$sum": "$total"}}}]))
    top_productos = list(
        db.pedidos.aggregate(
            [
                {"$unwind": "$detalles"},
                {
                    "$group": {
                        "_id": "$detalles.producto",
                        "importe": {
                            "$sum": {
                                "$multiply": [
                                    "$detalles.precio",
                                    "$detalles.cantidad",
                                    {"$subtract": [1, "$detalles.descuento"]},
                                ]
                            }
                        },
                    }
                },
                {"$sort": {"importe": -1}},
                {"$limit": 5},
            ]
        )
    )
    por_pais = list(
        db.pedidos.aggregate(
            [
                {"$group": {"_id": "$envio.pais", "importe": {"$sum": "$total"}}},
                {"$sort": {"importe": -1}},
                {"$limit": 5},
            ]
        )
    )
    return render_template(
        "panel.html",
        n_clientes=db.clientes.count_documents({}),
        n_productos=db.productos.count_documents({}),
        n_pedidos=db.pedidos.count_documents({}),
        ventas=ventas[0]["t"] if ventas else 0,
        top_productos=top_productos,
        por_pais=por_pais,
        recientes=list(db.pedidos.find().sort("_id", DESCENDING).limit(6)),
    )


# ------------------------------------------------------------------- clientes
CAMPOS_CLIENTE = ["empresa", "contacto", "cargo", "direccion", "ciudad", "region", "cp", "pais", "telefono"]


def generar_codigo(empresa):
    base = (re.sub(r"[^A-Za-z]", "", empresa).upper() + "XXXXX")[:5]
    codigo, n = base, 0
    while db.clientes.find_one({"_id": codigo}):
        n += 1
        codigo = base[:4] + str(n % 10) if n < 10 else base[:3] + f"{n:02d}"
    return codigo


@app.route("/clientes")
def clientes():
    q = request.args.get("q", "").strip()
    filtro = buscar(q, ["empresa", "contacto", "ciudad", "pais"])
    docs, pag = paginar(db.clientes, filtro, [("empresa", 1)], request.args.get("p", 1, type=int))
    return render_template("clientes.html", docs=docs, pag=pag, q=q)


@app.route("/clientes/nuevo", methods=["GET", "POST"])
@app.route("/clientes/<cid>/editar", methods=["GET", "POST"])
def cliente_form(cid=None):
    cliente = db.clientes.find_one({"_id": cid}) if cid else {}
    if cid and not cliente:
        return redirect(url_for("clientes"))
    if request.method == "POST":
        datos = {c: request.form.get(c, "").strip() or None for c in CAMPOS_CLIENTE}
        if not datos["empresa"]:
            flash("La empresa es obligatoria.", "error")
            return render_template("cliente_form.html", cliente={**cliente, **datos})
        if cid:
            db.clientes.update_one({"_id": cid}, {"$set": datos})
            db.pedidos.update_many({"cliente_id": cid}, {"$set": {"cliente_nombre": datos["empresa"]}})
            flash("Cliente actualizado.", "ok")
        else:
            db.clientes.insert_one({"_id": generar_codigo(datos["empresa"]), **datos})
            flash("Cliente creado.", "ok")
        return redirect(url_for("clientes"))
    return render_template("cliente_form.html", cliente=cliente)


@app.route("/clientes/<cid>/eliminar", methods=["POST"])
def cliente_eliminar(cid):
    if db.pedidos.count_documents({"cliente_id": cid}):
        flash("No se puede eliminar: el cliente tiene pedidos.", "error")
    else:
        db.clientes.delete_one({"_id": cid})
        flash("Cliente eliminado.", "ok")
    return redirect(url_for("clientes"))


# ------------------------------------------------------------------ productos
def opciones_embebidas(campo):
    """Lista las categorías o proveedores que ya existen dentro de los productos."""
    filas = db.productos.aggregate(
        [{"$group": {"_id": f"${campo}.nombre", "doc": {"$first": f"${campo}"}}}, {"$sort": {"_id": 1}}]
    )
    return [f["doc"] for f in filas]


@app.route("/productos")
def productos():
    q = request.args.get("q", "").strip()
    filtro = buscar(q, ["nombre", "categoria.nombre", "proveedor.nombre"])
    docs, pag = paginar(db.productos, filtro, [("nombre", 1)], request.args.get("p", 1, type=int))
    return render_template("productos.html", docs=docs, pag=pag, q=q)


@app.route("/productos/nuevo", methods=["GET", "POST"])
@app.route("/productos/<int:pid>/editar", methods=["GET", "POST"])
def producto_form(pid=None):
    producto = db.productos.find_one({"_id": pid}) if pid else {}
    if pid and not producto:
        return redirect(url_for("productos"))
    categorias, proveedores = opciones_embebidas("categoria"), opciones_embebidas("proveedor")
    if request.method == "POST":
        f = request.form
        datos = {
            "nombre": f.get("nombre", "").strip(),
            "cantidad_por_unidad": f.get("cantidad_por_unidad", "").strip(),
            "precio": numero(f.get("precio")),
            "existencias": numero(f.get("existencias"), int),
            "descontinuado": f.get("descontinuado") == "on",
            "categoria": next((c for c in categorias if c["nombre"] == f.get("categoria")), None),
            "proveedor": next((p for p in proveedores if p["nombre"] == f.get("proveedor")), None),
        }
        if not datos["nombre"] or not datos["categoria"] or not datos["proveedor"]:
            flash("Nombre, categoría y proveedor son obligatorios.", "error")
            return render_template(
                "producto_form.html", producto={**producto, **datos}, categorias=categorias, proveedores=proveedores
            )
        if pid:
            db.productos.update_one({"_id": pid}, {"$set": datos})
            flash("Producto actualizado.", "ok")
        else:
            db.productos.insert_one({"_id": siguiente_id(db.productos), "en_pedido": 0, "nivel_reorden": 0, **datos})
            flash("Producto creado.", "ok")
        return redirect(url_for("productos"))
    return render_template("producto_form.html", producto=producto, categorias=categorias, proveedores=proveedores)


@app.route("/productos/<int:pid>/eliminar", methods=["POST"])
def producto_eliminar(pid):
    db.productos.delete_one({"_id": pid})  # los pedidos conservan nombre y precio de la venta
    flash("Producto eliminado.", "ok")
    return redirect(url_for("productos"))


# -------------------------------------------------------------------- pedidos
@app.route("/pedidos")
def pedidos():
    q = request.args.get("q", "").strip()
    filtro = buscar(q, ["cliente_nombre", "envio.pais", "transportista"])
    if q.isdigit():
        filtro = {"$or": [filtro, {"_id": int(q)}]}
    docs, pag = paginar(db.pedidos, filtro, [("_id", -1)], request.args.get("p", 1, type=int))
    return render_template("pedidos.html", docs=docs, pag=pag, q=q)


@app.route("/pedidos/<int:oid>")
def pedido(oid):
    doc = db.pedidos.find_one({"_id": oid})
    if not doc:
        return redirect(url_for("pedidos"))
    empleado = db.empleados.find_one({"_id": doc["empleado_id"]})
    return render_template("pedido.html", p=doc, empleado=empleado)


@app.route("/pedidos/nuevo", methods=["GET", "POST"])
def pedido_nuevo():
    if request.method == "POST":
        f = request.form
        cliente = db.clientes.find_one({"_id": f.get("cliente")})
        lineas = []
        for pid, cant in zip(f.getlist("producto"), f.getlist("cantidad")):
            prod = db.productos.find_one({"_id": numero(pid, int, -1)})
            cant = numero(cant, int)
            if prod and cant > 0:
                lineas.append(
                    {"producto_id": prod["_id"], "producto": prod["nombre"], "precio": prod["precio"],
                     "cantidad": cant, "descuento": 0.0}
                )
        if not cliente or not lineas:
            flash("Elige un cliente y al menos un producto con cantidad.", "error")
        else:
            db.pedidos.insert_one(
                {
                    "_id": siguiente_id(db.pedidos),
                    "cliente_id": cliente["_id"],
                    "cliente_nombre": cliente["empresa"],
                    "empleado_id": numero(f.get("empleado"), int),
                    "fecha": date.today().isoformat(),
                    "fecha_requerida": None,
                    "fecha_envio": None,
                    "transportista": f.get("transportista"),
                    "flete": numero(f.get("flete")),
                    "envio": {"nombre": cliente["empresa"], "direccion": cliente.get("direccion"),
                              "ciudad": cliente.get("ciudad"), "pais": cliente.get("pais")},
                    "detalles": lineas,
                    "total": round(sum(l["precio"] * l["cantidad"] for l in lineas), 2),
                }
            )
            flash("Pedido creado.", "ok")
            return redirect(url_for("pedidos"))
    return render_template(
        "pedido_form.html",
        clientes=list(db.clientes.find().sort("empresa", 1)),
        empleados=list(db.empleados.find().sort("apellido", 1)),
        productos=list(db.productos.find({"descontinuado": False}).sort("nombre", 1)),
        transportistas=sorted(db.pedidos.distinct("transportista")),
    )


@app.route("/pedidos/<int:oid>/eliminar", methods=["POST"])
def pedido_eliminar(oid):
    db.pedidos.delete_one({"_id": oid})
    flash("Pedido eliminado.", "ok")
    return redirect(url_for("pedidos"))


if __name__ == "__main__":
    # Puerto 5001: en Mac el 5000 lo ocupa AirPlay Receiver
    app.run(debug=True, port=5001)
