# Formulario comercial de inout.cl

La ruta `POST /api/contacto/cotizaciones/` recibe las consultas para cotizar servicios. Es una vista pública independiente: no usa modelos, endpoints, autenticación, tokens, almacenamiento ni flujos de postulantes. Tampoco guarda los datos del formulario en la base de datos.

## Render

El despliegue actual de Render es `backendinout.onrender.com`. Al publicar este cambio, la web envía las consultas a:

`https://backendinout.onrender.com/api/contacto/cotizaciones/`

`CONTACT_ALLOWED_ORIGINS` tiene por defecto `https://www.inout.cl,https://inout.cl`. Si el dominio público cambia, actualizar esta variable en el Web Service de Render. Se puede agregar `http://localhost:5188` temporalmente al desarrollar en local. El cliente web debe compilar con `VITE_CONTACT_ENDPOINT` apuntando a la URL pública del backend; el fallback del sitio usa el dominio actual del portal de postulaciones.

Render ya exige `REDIS_URL` para Channels. La vista usa ese Redis para aplicar 5 solicitudes por IP y 500 globales por hora, y para evitar reenvíos de una misma referencia por 24 horas. Render coloca la IP cliente al inicio de `X-Forwarded-For`; los datos de ese encabezado se usan solo para el límite de solicitudes, junto a un tope global. En desarrollo local usa la caché de Django.

## Correo

La vista reutiliza la configuración SMTP existente del servicio Django. Variables necesarias en el entorno del Web Service de Render:

- `EMAIL_HOST`: host SMTP del proveedor del buzón.
- `EMAIL_PORT`: puerto, habitualmente 587 con TLS o 465 con SSL.
- `EMAIL_HOST_USER`: cuenta SMTP autorizada para enviar.
- `EMAIL_HOST_PASSWORD`: contraseña o clave de aplicación guardada como secret en Render.
- `EMAIL_USE_TLS=true` para STARTTLS, o `EMAIL_USE_SSL=true` para SSL directo; no habilitar ambos.
- `DEFAULT_FROM_EMAIL`: remitente autorizado, idealmente `contacto@inout.cl` o una dirección del mismo dominio validada por el proveedor.

El destinatario está fijado en el servidor a `contacto@inout.cl`. `Reply-To` se configura con el correo validado del cliente. El contenido se envía como texto plano. Cuando SMTP no está configurado o no acepta el mensaje, el endpoint devuelve un error y no informa un envío exitoso.

En Render: Dashboard → Web Service `backendinout` → **Environment**. Agregar los valores faltantes, guardar y desplegar. No introducir credenciales en `VITE_*`, GitHub, el frontend ni esta documentación. Las variables de correo preexistentes también son usadas por notificaciones del sistema, incluidas las de postulaciones; no cambiar sus valores si esas notificaciones ya funcionan.

## Campos

JSON: `name`, `email`, `phone`, `company`, `service`, `commune`, `message`, `website` (campo trampa vacío) y `request_id` UUID v4. Nombre, correo, servicio y mensaje son obligatorios. El correo recibe el límite de tamaño de 20 KB.

El navegador envía `application/json`, lo que dispara el preflight CORS del portal. El middleware CORS del backend ya admite los orígenes de la web pública; además, esta vista valida `Origin` contra `CONTACT_ALLOWED_ORIGINS` y rechaza solicitudes sin origen autorizado. No agregar `AllowAny` a toda la API ni restringir el CORS global: el portal público de postulaciones y sus clientes conservan el comportamiento actual.

## Despliegue y comprobación

Render enlaza este backend al repositorio `BackendInOut` en la rama `main`; un push a esa rama puede iniciar el despliegue automáticamente. Después de que el nuevo deploy esté listo:

1. Comprobar `OPTIONS /api/contacto/cotizaciones/` desde `https://www.inout.cl` y que el preflight CORS permita `POST` y `Content-Type`.
2. Enviar desde el formulario una consulta de prueba acordada e identificarla en la casilla `contacto@inout.cl`.
3. Comprobar que responder al mensaje va al correo del remitente.
4. Revisar tanto `https://www.inout.cl` como `https://postulaciones.inout.cl`; las rutas de postulaciones no deben cambiar.

El backend retorna `202` solo cuando Django confirma que SMTP aceptó un mensaje. Revisar la bandeja y el registro de entrega del proveedor confirma la recepción efectiva.
