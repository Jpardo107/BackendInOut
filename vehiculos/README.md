# Gestión de vehículos

El administrador web permite crear y editar vehículos, programar el kilometraje
de mantención y consultar su historial. Un vehículo sin movimientos puede
eliminarse; con historial debe desactivarse para conservar los registros. No se
puede desactivar ni eliminar mientras esté pendiente su entrega.

La app de supervisión muestra recepción para vehículos disponibles y entrega
para los que están a cargo del usuario. Cada registro exige kilometraje no
decreciente, cinco fotos (frontal, trasera, izquierdo, derecho y tablero), y la
respuesta a los cuatro elementos del checklist. Se admiten hasta quince fotos
adicionales. Cada foto tiene su propio indicador y descripción de novedades.
Un resumen vacío se guarda como «Recepción sin observaciones» o «Entrega sin
observaciones». El kilometraje de mantención genera un aviso visual, sin bloquear
la entrega ni la recepción.

## Instalación

```sh
python manage.py migrate vehiculos
python manage.py test vehiculos
```

Utiliza las variables R2 existentes (`R2_BUCKET_NAME`, `R2_ENDPOINT_URL`,
`R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`). Las fotos se almacenan bajo
`vehiculos/` y se consultan mediante URLs firmadas tras verificar permisos.
No requiere dependencias nuevas. Compilar y desplegar ambos frontends junto con
el backend; ambos conservan su configuración `VITE_API_PROD` actual.

## API

- `GET/POST /api/vehiculos/`: listado con capacidades / alta administrativa.
- `GET/PATCH/DELETE /api/vehiculos/{id}/`: consulta / edición / eliminación.
- `POST /api/vehiculos/{id}/movimiento/`: recepción o entrega del supervisor.
- `GET /api/vehiculos/{id}/historial/?page=1`: historial, diez registros por página.
- `GET /api/vehiculos/{id}/foto/?foto={foto_id}`: URL firmada por una hora.

El movimiento usa multipart con `datos` (JSON) y `foto_0`, `foto_1`, etc. En `datos`
se envían `solicitud_id` (UUID de reintento), `version` (del vehículo consultado),
`tipo` (`recepcion` o `entrega`), `kilometraje`, `gata`, `llave_cruz`, `extintor`,
`triangulo`, `resumen` y `fotos` (lista de `{vista, tiene_novedad, novedad}`).
Las fotos aceptan JPG, PNG y WebP de hasta 10 MB; el frontend convierte HEIC.

Solo supervisores registran movimientos, siempre a su propio nombre. Los roles
administrativos, RRHH, Controller y jefaturas/gerencias de operaciones administran
la flota; usuarios staff/superuser también. El supervisor solo puede consultar
sus propios movimientos y fotos, mientras administración ve el historial completo.

## Consistencia

Las fotos se validan y suben antes de cambiar la custodia. Al guardar se vuelve a
validar el estado dentro de una transacción, con bloqueo de fila y actualización
condicionada a la versión. Un conflicto devuelve HTTP 409 sin liberar el vehículo.
La entrega solo puede cerrar la recepción vigente de su supervisor. Cada UUID de
solicitud es único: reintentar un registro ya guardado devuelve el mismo movimiento
sin duplicarlo. Los errores revierten el cambio de estado y limpian las fotos
subidas durante el intento, registrando cualquier fallo de limpieza en el log.

Las pruebas cubren traspaso, fotografías y novedades, permisos, kilometraje,
checklist, fallos de almacenamiento/base de datos, reintentos y solicitudes que
compiten por el mismo vehículo durante la subida de imágenes.
