# Northwind renovado (Flask + MongoDB)

Reingeniería del sistema legacy **Northwind** (base relacional con formularios y reportes de Access) a una app web con **Python, Flask y MongoDB**.

## Cómo correrlo

1. **Levantar MongoDB** (la forma más fácil, con Docker):
   ```bash
   docker run -d --name mongo -p 27017:27017 mongo
   ```
   (o instala MongoDB Community con Homebrew y arranca el servicio)

2. **Instalar dependencias**:
   ```bash
   python3 -m venv venv && source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Migrar los datos del sistema legacy a MongoDB**:
   ```bash
   python migrar.py
   ```
   Se pueden repetir las veces que se quiera: borra y vuelve a crear las colecciones.

4. **Abrir la app**:
   ```bash
   python app.py
   ```
   Entra a http://localhost:5001 (el 5000 lo usa AirPlay en Mac).

Si Mongo corre en otro lado: `MONGO_URI="mongodb://host:27017" python app.py`.

## Estructura

```
app.py              rutas de Flask (panel, clientes, productos, pedidos)
migrar.py           migración relacional -> documentos
datos/northwind_legacy.db   base legacy de demo (8 tablas, 830 pedidos, 2,155 líneas)
templates/, static/ vistas y estilos
```

## De tablas a colecciones

| Legacy (relacional)                    | MongoDB                                        |
|----------------------------------------|------------------------------------------------|
| Customers                              | `clientes`                                     |
| Employees                              | `empleados`                                    |
| Products + Categories + Suppliers      | `productos` (categoría y proveedor embebidos)  |
| Orders + Order Details + Shippers      | `pedidos` (líneas y transportista embebidos)   |

Ejemplo de un documento de `pedidos`:

```json
{
  "_id": 10248,
  "cliente_id": "VINET",
  "cliente_nombre": "Vins et alcools Chevalier",
  "empleado_id": 5,
  "fecha": "2016-07-04",
  "transportista": "Federal Shipping",
  "flete": 16.75,
  "envio": { "nombre": "...", "direccion": "...", "ciudad": "Reims", "pais": "France" },
  "detalles": [
    { "producto_id": 11, "producto": "Queso Cabrales", "precio": 14.0, "cantidad": 12, "descuento": 0.0 }
  ],
  "total": 440.0
}
```

**Por qué embebidos:** un pedido casi siempre se consulta junto con sus productos, así que se guarda todo en un solo documento y se evitan los JOIN del modelo relacional. El nombre y precio del producto quedan "congelados" en el pedido, como en una factura.

## Qué hace la app

- **Panel:** ventas totales, conteos, productos más vendidos y ventas por país.
- **Clientes y productos:** listar, buscar, crear, editar y eliminar (un cliente con pedidos no se puede eliminar).
- **Pedidos:** listar, buscar, ver detalle, crear (con varias líneas) y eliminar.
