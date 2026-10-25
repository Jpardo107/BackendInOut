# Planificación personal

Módulo privado de Jaime Pardo, RUT `17511942-6`. El menú y la ruta del frontend comprueban el RUT; todos los endpoints del servidor vuelven a comprobarlo sobre el usuario autenticado y activo. No hay excepción por cargo, staff o superusuario. Cada consulta y edición está limitada al propietario.

## Uso

- **Mi día:** fecha local del dispositivo por defecto, navegación a fechas anteriores o futuras, plantillas de ingreso rápido, estados planificada/realizada/cancelada y edición/eliminación. Los horarios manuales usan selectores de hora y minutos `00`/`30`. El término es opcional; si es anterior al inicio corresponde al día siguiente.
- **Mi pauta:** ciclos configurables de 1–31 días de trabajo y 1–31 libres; atajos 4×4, 5×2, 6×1, 7×7 y 2×2; jornadas diurna, nocturna, AM y PM y horarios configurables. La fecha de inicio es el primer día de trabajo. Una nueva fecha crea una versión, conservando las anteriores. Guardar sobre una fecha existente actualiza esa versión previa confirmación.
- **Ajustar día:** trabajo, descanso o turno extra para una fecha concreta. No desplaza el ciclo. El extra comienza planificado y solo entra al resumen cuando se marca realizado. Restaurar elimina la excepción y recupera la pauta base.
- **Resumen:** fecha o rango de hasta 366 días, tipo de actividad y franja horaria opcional. Filtra por la fecha y hora **de inicio** de cada registro. Una franja 20:00–08:00 incluye inicios nocturnos en cada una de las fechas del rango; no es un filtro por intersección de intervalos. Permite copiar un texto con formato WhatsApp o seleccionar el texto si el navegador bloquea el portapapeles. Cambiar filtros invalida la vista previa anterior.

## Registros integrados

No se copian ni modifican los registros de los módulos originales. Se consultan al abrir/actualizar el panel y al volver a la aplicación:

| Origen | Propietario | Fecha utilizada |
| --- | --- | --- |
| Supervisión y solicitud asociada | `supervisor` | Fecha y hora de inicio registradas |
| Movimiento de inventario, por categoría (vestuario/equipo, cargo fijo, útiles de aseo) | `usuario_registro` | Creación convertida a zona del dispositivo |
| Informe generado | `usuario_creador` | Creación convertida a zona del dispositivo |
| Rendición | `supervisor` | Creación convertida a zona del dispositivo |
| Movimiento de vehículo | `supervisor` | Creación convertida a zona del dispositivo |

Los horarios automáticos conservan sus minutos originales. Las solicitudes y los movimientos muestran el estado **actual**, no un estado histórico reconstruido. Los despachos, devoluciones y ajustes se describen con su tipo y estado originales; no se presentan todos como entregas recibidas. La solicitud y la supervisión son dos registros distintos y se desglosan por tipo; el total no representa horas trabajadas.

Una actividad manual realizada puede vincularse con un registro original. El servidor valida que exista y pertenezca al mismo usuario. El plan vinculado se conserva en la agenda y se excluye del conteo: cuenta el registro original en su fecha y categoría. Si el original se elimina posteriormente, el plan mantiene su referencia y puede desvincularse al editarlo.

## Instalación

1. Desplegar el backend con la app `planificacion` y ejecutar `python manage.py migrate`. La migración `planificacion/0001_initial.py` agrega tres tablas sin modificar registros de otros módulos.
2. Compilar/publicar el frontend de supervisión con su `VITE_API_PROD` habitual: `npm run build`.
3. Iniciar sesión con el usuario cuyo RUT sea `17511942-6`; el menú mostrará **Planificación**. Configurar la primera pauta con la fecha real de inicio.

No se configura una pauta de producción por defecto ni se generan actividades reales durante la instalación.

## Validación

```sh
.venv/bin/python manage.py test planificacion supervision inventario vehiculos --settings=documentacion.test_settings --noinput
.venv/bin/python manage.py makemigrations --check --dry-run --settings=documentacion.test_settings
```

Las pruebas usan una base SQLite temporal y cubren acceso, aislamiento, CRUD, ciclos, cambios de pauta, excepciones, turnos nocturnos, minutos permitidos, fecha local, fuentes automáticas, vínculos sin duplicación y filtros.
