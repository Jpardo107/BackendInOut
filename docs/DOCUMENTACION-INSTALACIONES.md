# Documentación de instalaciones: catálogo y reinicio

Cambios del 21 de octubre de 2026. El catálogo fijo del panel fue sustituido por tipos persistentes en `TipoDocumentoInstalacion`. No se agregan nombres iniciales: el administrador crea los nuevos desde cero.

## Uso

En **Instalaciones → Documentación → Administrar documentos** se pueden crear, consultar, renombrar, ordenar y eliminar los tipos. Los cambios alimentan las columnas, la estadística, el Excel y el gráfico de cumplimiento del inicio. Una clave interna estable mantiene la asociación de los archivos cuando se renombra un tipo. Se permite un archivo por tipo e instalación, con reemplazo y eliminación del archivo/vista previa desde su detalle. Para eliminar un tipo cargado hay que eliminar primero sus archivos.

El catálogo usa los mismos permisos administrativos que Zonas (staff, superusuario y cargos administrativos/RRHH). Los usuarios autenticados pueden consultarlo. `DocumentoItem` y `EstadoDocumentacion`, usados por las supervisiones, permanecen independientes.

## Despliegue

1. Subir el código de `documentacion/` al repositorio `Jpardo107/BackendInOut` y desplegar el backend.
2. Ejecutar `python manage.py migrate` en la consola de ese servicio, con la base de producción. La migración `documentacion.0004` es aditiva y no borra archivos ni registros.
3. Detener temporalmente las cargas/reemplazos en documentación mientras se hace el reinicio.
4. Revisar el inventario y ejecutar la limpieza indicada abajo.
5. Publicar el frontend compilado de `frontend administracion/admin-inout`. No cambiar las URLs de producción; el nuevo endpoint se deriva de `VITE_API_PROD_S3` y puede configurarse con `VITE_API_PROD_TIPOS_DOCUMENTO`.
6. Crear el catálogo nuevo desde el botón del módulo.

## Reinicio solicitado

Desde **la consola del backend en Render**, después del despliegue y la migración:

```bash
python manage.py reiniciar_documentacion_instalaciones
```

El comando anterior solo cuenta. Para realizar el borrado solicitado:

```bash
python manage.py reiniciar_documentacion_instalaciones \
  --execute \
  --confirm REINICIAR_DOCUMENTACION_INSTALACIONES \
  --manifest /tmp/reinicio-documentacion-instalaciones-20261021.json
```

El archivo de inventario debe ser nuevo; si hay que reintentar, utiliza otro nombre. Descárgalo si deseas conservar la constancia fuera del filesystem temporal de Render. Es un inventario, no una copia de los documentos.

El comando elimina originales y vistas previas de cada registro y luego los objetos huérfanos de las rutas **`documentos/instalacion_ID/`** y **`documentos/previews/instalacion_ID/`**. Finalmente elimina los tipos inventariados y verifica que no queden registros, tipos ni objetos en ese ámbito. No toca otros prefijos, documentos laborales de amonestaciones, postulaciones, informes, datos de instalaciones, usuarios o historial de supervisiones. Tampoco modifica el estado administrativo de las directivas.

Si R2 falla, conserva el registro del archivo fallido y el catálogo para reintentar; los registros eliminados con éxito permanecen eliminados. El comando se detiene con error si hubo fallos o nuevas cargas durante el proceso. No se ejecuta desde una base SQLite local por defecto, para evitar eliminar archivos del bucket productivo dejando intactos los registros online. `--allow-sqlite` está destinado a entornos aislados de pruebas.

## Verificación

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python manage.py test \
  documentacion instalacion supervision user backend_inout \
  --settings=documentacion.test_settings --noinput

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python manage.py makemigrations \
  --check --dry-run --settings=documentacion.test_settings
```

Las pruebas usan base temporal y almacenamiento simulado, nunca el bucket real. Cubren CRUD/permisos, nombres duplicados, renombrado, carga y reemplazo, unicidad, eliminación con fallo de storage, inventario sin borrado, limpieza limitada al módulo, conservación de supervisiones/amonestaciones y errores parciales. Pasaron 63 pruebas. El frontend compila con `npm run build` y la revisión ESLint de los archivos cambiados no tiene errores.

## Estado del trabajo

Se realizó únicamente inventario de Cloudflare: **130 objetos, 322.164.135 bytes** en rutas de instalaciones y previews. La configuración local usa SQLite y contiene un documento cuyo archivo no aparece en ese inventario. No se dispone de la conexión de producción. El usuario eligió ejecutar el comando en Render. **El borrado productivo aún no se ha ejecutado**; el comando anterior está preparado para hacerlo dentro del servicio correcto.
