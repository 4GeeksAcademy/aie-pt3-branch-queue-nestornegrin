# Gestor de turnos — Banco Meridional

Gestor de colas por tipo de servicio para sucursales bancarias, en Python y por terminal.

- Tres colas independientes: `deposito`, `retiro` y `gestion_cuenta`.
- Números de ticket globales y secuenciales entre todos los servicios.
- Cada cola atiende en estricto orden de llegada (FIFO).
- Solo usa la biblioteca estándar de Python (`collections.deque`, `datetime`, `threading`).

## Requisitos

Python 3.10 o superior.

## Cómo ejecutarlo

    python3 branch_queue.py

## Operaciones de `BranchQueue`

| Método | Descripción |
|---|---|
| `issue_ticket(client_name, service_type)` | Crea y encola un ticket en su servicio. Rechaza servicios inválidos. |
| `call_next(service_type)` | Extrae el siguiente cliente de ese servicio. Lanza `EmptyServiceQueueError` si no hay nadie. |
| `peek_next(service_type)` | Muestra el siguiente cliente sin retirarlo. |
| `list_waiting()` | Devuelve `{servicio: [tickets en orden]}`. |
| `stats()` | Devuelve el número de clientes por servicio y la clave `total`. |

## Estructura

    branch_queue.py   # Modelo (Ticket), gestor (BranchQueue), CLI y punto de entrada
    DESIGN.md         # Decisiones de diseño y escenario concurrente

Las decisiones técnicas están explicadas en [DESIGN.md](DESIGN.md).