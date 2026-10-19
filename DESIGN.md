# Notas de diseño — Gestor de turnos de Banco Meridional

## 1. Por qué una cola separada por tipo de servicio

`BranchQueue` guarda un diccionario con una `collections.deque` por servicio:

    {
        "deposito":       deque([...]),
        "retiro":         deque([...]),
        "gestion_cuenta": deque([...]),
    }

y un único contador global (`itertools.count(1)`) para numerar los tickets.

### Coste de `call_next(service_type)`

| Estructura | Cómo encuentra al siguiente | Coste |
|---|---|---|
| Una sola lista compartida | Recorrer la lista desde el principio hasta el primer ticket de ese servicio y luego eliminarlo del medio, desplazando el resto. | **O(n)**, siendo n todos los clientes de la sucursal |
| **Una `deque` por servicio (elegida)** | Buscar la cola en el diccionario y hacer `popleft()`. | **O(1)**, sin importar cuántos clientes haya |

Con una lista única, el agente de depósitos tiene que "recorrer toda la sala": si hay 50 personas esperando un retiro delante del primer cliente de depósitos, las revisa todas. Es exactamente el problema del sistema en papel. Con colas separadas, cada agente solo mira su propia cola y llama al primero al instante.

### Por qué `deque` y no `list`

`list.pop(0)` es O(n) porque desplaza todos los elementos restantes. `deque.popleft()` es O(1). Insertar al final es O(1) en ambas.

### Numeración global

El contador es independiente de las colas: cada ticket recibe `next(contador)` sin importar su servicio. Así dos clientes nunca comparten número aunque estén en colas distintas. El tipo de servicio se valida **antes** de pedir el número, de modo que un ticket rechazado no deja huecos en la numeración.

## 2. Dos agentes del mismo servicio llaman a `call_next` a la vez

### Qué podría fallar sin protección

`call_next` hace dos cosas: **comprobar** si hay alguien en la cola y **extraer** al primero. Si dos agentes intercalan esos pasos:

1. Agente A mira la cola: el primero es el ticket #7.
2. Agente B mira la cola: el primero también es el #7.
3. Los dos anuncian al #7 → **el mismo cliente es llamado dos veces**, o uno de los dos se queda con la cola vacía y falla.

### Orden de mutación correcto

**La primera mutación debe ser retirar el ticket de la cola.** Retirarlo es lo que lo "reclama" para un agente. Solo después se anuncia o se atiende.

Implementación con un `threading.Lock` compartido:

1. Adquirir el lock.
2. Comprobar que la cola del servicio no está vacía.
3. `popleft()`: el ticket sale de la cola. Desde este instante ningún otro agente puede verlo.
4. Liberar el lock.
5. Anunciar el ticket en pantalla, fuera del lock.

Como los pasos 2 y 3 ocurren dentro del mismo bloqueo, el segundo agente recibe el ticket #8 o, si no hay más, un aviso de cola vacía. Nunca el #7 otra vez.

El error contrario sería **anunciar primero y retirar después** (o hacer `peek_next` y luego `call_next` por separado para "reservar" a un cliente): entre ambos pasos otro agente puede llamar al mismo cliente.

### Emisión concurrente de tickets

`issue_ticket` también usa el lock: obtener el número y encolar el ticket ocurren juntos. Así no se repiten números y el orden dentro de cada cola coincide con el orden de numeración.

### Posible mejora

Un lock por servicio permitiría que el agente de depósitos y el de retiros nunca se esperen entre sí. En esta versión se usa un solo lock porque el contador global es compartido y la contención es mínima en una sucursal.