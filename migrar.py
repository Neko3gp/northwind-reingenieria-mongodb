"""
migrar.py - Reingeniería de datos: Northwind (relacional) -> MongoDB (documentos)

Lee la base legacy (datos/northwind_legacy.db) y la convierte en 4 colecciones:
  clientes, empleados, productos (con categoría y proveedor embebidos),
  pedidos (con sus líneas de detalle embebidas).

Uso:  python migrar.py
"""
import os
import sqlite3

from pymongo import MongoClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("MONGO_DB", "northwind")
LEGACY_DB = os.path.join(os.path.dirname(__file__), "datos", "northwind_legacy.db")


def filas(cur, sql):
    """Ejecuta una consulta y regresa una lista de diccionarios."""
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, fila)) for fila in cur.fetchall()]


def main():
    legacy = sqlite3.connect(LEGACY_DB)
    cur = legacy.cursor()
    db = MongoClient(MONGO_URI)[DB_NAME]

    # Empezamos de cero para poder repetir la migración sin duplicados
    for nombre in ("clientes", "empleados", "productos", "pedidos"):
        db[nombre].drop()

    # --- clientes -------------------------------------------------------
    clientes = [
        {
            "_id": c["CustomerID"],
            "empresa": c["CompanyName"],
            "contacto": c["ContactName"],
            "cargo": c["ContactTitle"],
            "direccion": c["Address"],
            "ciudad": c["City"],
            "region": c["Region"],
            "cp": c["PostalCode"],
            "pais": c["Country"],
            "telefono": c["Phone"],
        }
        for c in filas(cur, "SELECT * FROM Customers")
    ]
    db.clientes.insert_many(clientes)

    # --- empleados ------------------------------------------------------
    empleados = [
        {
            "_id": e["EmployeeID"],
            "nombre": e["FirstName"],
            "apellido": e["LastName"],
            "cargo": e["Title"],
            "fecha_contratacion": e["HireDate"],
            "ciudad": e["City"],
            "pais": e["Country"],
            "telefono": e["HomePhone"],
        }
        for e in filas(cur, "SELECT * FROM Employees")
    ]
    db.empleados.insert_many(empleados)

    # --- productos (categoría y proveedor van DENTRO del producto) -------
    categorias = {c["CategoryID"]: c for c in filas(cur, "SELECT * FROM Categories")}
    proveedores = {s["SupplierID"]: s for s in filas(cur, "SELECT * FROM Suppliers")}
    productos = []
    for p in filas(cur, "SELECT * FROM Products"):
        cat = categorias[p["CategoryID"]]
        prov = proveedores[p["SupplierID"]]
        productos.append(
            {
                "_id": p["ProductID"],
                "nombre": p["ProductName"],
                "cantidad_por_unidad": p["QuantityPerUnit"],
                "precio": float(p["UnitPrice"]),
                "existencias": p["UnitsInStock"],
                "en_pedido": p["UnitsOnOrder"],
                "nivel_reorden": p["ReorderLevel"],
                "descontinuado": str(p["Discontinued"]) == "1",
                "categoria": {"nombre": cat["CategoryName"], "descripcion": cat["Description"]},
                "proveedor": {
                    "nombre": prov["CompanyName"],
                    "contacto": prov["ContactName"],
                    "ciudad": prov["City"],
                    "pais": prov["Country"],
                },
            }
        )
    db.productos.insert_many(productos)
    nombre_producto = {p["_id"]: p["nombre"] for p in productos}
    nombre_cliente = {c["_id"]: c["empresa"] for c in clientes}
    transportistas = {s["ShipperID"]: s["CompanyName"] for s in filas(cur, "SELECT * FROM Shippers")}

    # --- pedidos (las líneas de detalle van DENTRO del pedido) -----------
    detalles = {}
    for d in filas(cur, 'SELECT * FROM "Order Details"'):
        detalles.setdefault(d["OrderID"], []).append(
            {
                "producto_id": d["ProductID"],
                "producto": nombre_producto[d["ProductID"]],
                "precio": float(d["UnitPrice"]),
                "cantidad": d["Quantity"],
                "descuento": float(d["Discount"]),
            }
        )

    pedidos = []
    for o in filas(cur, "SELECT * FROM Orders"):
        lineas = detalles.get(o["OrderID"], [])
        total = sum(l["precio"] * l["cantidad"] * (1 - l["descuento"]) for l in lineas)
        pedidos.append(
            {
                "_id": o["OrderID"],
                "cliente_id": o["CustomerID"],
                "cliente_nombre": nombre_cliente.get(o["CustomerID"], ""),
                "empleado_id": o["EmployeeID"],
                "fecha": o["OrderDate"],
                "fecha_requerida": o["RequiredDate"],
                "fecha_envio": o["ShippedDate"],
                "transportista": transportistas[o["ShipVia"]],
                "flete": float(o["Freight"]),
                "envio": {
                    "nombre": o["ShipName"],
                    "direccion": o["ShipAddress"],
                    "ciudad": o["ShipCity"],
                    "pais": o["ShipCountry"],
                },
                "detalles": lineas,
                "total": round(total, 2),
            }
        )
    db.pedidos.insert_many(pedidos)

    db.pedidos.create_index("cliente_id")
    db.pedidos.create_index("fecha")

    print("Migración terminada:")
    for nombre in ("clientes", "empleados", "productos", "pedidos"):
        print(f"  {nombre}: {db[nombre].count_documents({})} documentos")


if __name__ == "__main__":
    main()
