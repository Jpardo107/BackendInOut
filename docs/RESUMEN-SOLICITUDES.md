# Correo diario de solicitudes

De lunes a viernes a las 07:00 (hora Chile) se envía un correo con las solicitudes registradas en supervisiones durante las últimas 24 horas. El lunes cubre desde el viernes 07:00 para incluir el fin de semana. Cada fila trae supervisor, instalación, detalle y fecha y hora. Las supervisiones con "Sin solicitudes" no se incluyen. Si no hubo solicitudes, igual se envía un correo que lo indica.

Los destinatarios (hasta 20) y el interruptor de activación se configuran en el admin: **Supervisiones → Solicitudes → Correo diario**. Desde ahí también se puede enviar una prueba.

## Remitente

El correo diario y las alertas de stock de inventario salen desde `INFORMACIONES_FROM_EMAIL` (por defecto `informaciones@inout.cl`). La cuenta SMTP de `EMAIL_HOST_USER` debe tener permitido enviar como esa dirección (cuenta propia, alias o "enviar como"); si no, el servidor rechazará el correo. Si `informaciones@inout.cl` es una cuenta propia, usar sus credenciales en `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` cambia el remitente de **todos** los correos del sistema.

## Programación en Render

Crear un **Cron Job** en Render conectado al mismo repositorio y rama que el Web Service, con las mismas variables de entorno (base de datos y `EMAIL_*`):

- Command: `python manage.py enviar_resumen_solicitudes`
- Schedule: `0 10,11 * * 1-5` (UTC)

Corre a las 10:00 y 11:00 UTC porque Chile cambia de horario: el comando solo envía cuando en Chile son las 07 y registra el envío, así que nunca se manda dos veces el mismo día.

Para enviar manualmente (por ejemplo, desde la shell del Web Service): `python manage.py enviar_resumen_solicitudes --forzar`.
