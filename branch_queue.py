"""
Gestor de colas de atención para las sucursales de Banco Meridional.

- Cada tipo de servicio (deposito, retiro, gestion_cuenta) tiene su propia cola FIFO.
- Los números de ticket son globales y secuenciales entre todos los servicios.
- Solo usa la biblioteca estándar de Python.
"""

from __future__ import annotations

import itertools
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime


# ---------------------------------------------------------------------------
# Dominio
# ---------------------------------------------------------------------------

SERVICE_TYPES = ("deposito", "retiro", "gestion_cuenta")

SERVICE_LABELS = {
    "deposito": "Depósitos",
    "retiro": "Retiros",
    "gestion_cuenta": "Gestión de cuenta",
}


class InvalidServiceTypeError(ValueError):
    """Se lanza cuando se indica un tipo de servicio que no existe."""


class EmptyServiceQueueError(Exception):
    """Se lanza al llamar o consultar una cola de servicio vacía."""


@dataclass(frozen=True)
class Ticket:
    """Ticket emitido a un cliente. Inmutable una vez creado."""

    number: int
    client_name: str
    service_type: str
    issued_at: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        label = SERVICE_LABELS[self.service_type]
        return f"#{self.number:03d} {self.client_name} [{label}] emitido {self.issued_at:%H:%M:%S}"


# ---------------------------------------------------------------------------
# Gestor de colas
# ---------------------------------------------------------------------------

class BranchQueue:
    """
    Una deque por tipo de servicio + un contador global de tickets.

    - issue_ticket: O(1) -> append al final de la cola de su servicio.
    - call_next:    O(1) -> popleft de la cola de su servicio, sin mirar las demás.

    Un único Lock hace atómicas la numeración y la extracción, para que dos
    agentes nunca reciban el mismo ticket ni se repitan números.
    """

    def __init__(self) -> None:
        self._queues: dict[str, deque[Ticket]] = {service: deque() for service in SERVICE_TYPES}
        self._ticket_counter = itertools.count(1)
        self._lock = threading.Lock()

    @staticmethod
    def validate_service_type(service_type: str) -> str:
        """Normaliza el tipo de servicio y lo rechaza con un mensaje claro si no existe."""
        normalized = service_type.strip().lower() if isinstance(service_type, str) else ""
        if normalized not in SERVICE_TYPES:
            valid = ", ".join(SERVICE_TYPES)
            raise InvalidServiceTypeError(
                f"Tipo de servicio no válido: '{service_type}'. Opciones válidas: {valid}."
            )
        return normalized

    def issue_ticket(self, client_name: str, service_type: str) -> Ticket:
        """Crea un ticket con el siguiente número global y lo encola en su servicio."""
        # Validamos ANTES de numerar: una entrada inválida no consume número.
        service = self.validate_service_type(service_type)
        name = client_name.strip() if isinstance(client_name, str) else ""
        if not name:
            raise ValueError("El nombre del cliente no puede estar vacío.")

        with self._lock:
            ticket = Ticket(next(self._ticket_counter), name, service)
            self._queues[service].append(ticket)
        return ticket

    def call_next(self, service_type: str) -> Ticket:
        """Extrae y devuelve el cliente que más tiempo lleva esperando en ese servicio."""
        service = self.validate_service_type(service_type)
        with self._lock:
            queue = self._queues[service]
            if not queue:
                raise EmptyServiceQueueError(
                    f"No hay clientes esperando para {SERVICE_LABELS[service]}."
                )
            return queue.popleft()

    def peek_next(self, service_type: str) -> Ticket:
        """Devuelve el siguiente cliente de ese servicio sin retirarlo."""
        service = self.validate_service_type(service_type)
        with self._lock:
            queue = self._queues[service]
            if not queue:
                raise EmptyServiceQueueError(
                    f"No hay clientes esperando para {SERVICE_LABELS[service]}."
                )
            return queue[0]

    def list_waiting(self) -> dict[str, list[Ticket]]:
        """Devuelve una copia: {servicio: [tickets en orden de atención]}."""
        with self._lock:
            return {service: list(queue) for service, queue in self._queues.items()}

    def stats(self) -> dict[str, int]:
        """Devuelve el número de clientes por servicio y la clave 'total'."""
        with self._lock:
            counts = {service: len(queue) for service, queue in self._queues.items()}
        counts["total"] = sum(counts.values())
        return counts


# ---------------------------------------------------------------------------
# Interfaz de línea de comandos
# ---------------------------------------------------------------------------

class BranchCLI:
    """
    Menú de texto en bucle.
    Solo gestiona entrada y salida; la lógica de colas vive en BranchQueue.
    """

    MENU = (
        "\n=== Banco Meridional - Gestor de turnos ===\n"
        "1. Emitir ticket\n"
        "2. Llamar al siguiente cliente\n"
        "3. Ver siguiente cliente (sin llamarlo)\n"
        "4. Ver lista de espera\n"
        "5. Ver estadísticas\n"
        "6. Salir"
    )
    EXIT_OPTION = "6"

    # Atajos numéricos para no tener que escribir el nombre del servicio.
    SERVICE_SHORTCUTS = {"1": "deposito", "2": "retiro", "3": "gestion_cuenta"}
    SERVICE_PROMPT = (
        "Tipo de servicio (1=deposito, 2=retiro, 3=gestion_cuenta; Enter para cancelar): "
    )

    def __init__(self, branch_queue: BranchQueue | None = None) -> None:
        # Se puede inyectar un gestor (útil para tests); si no, se crea uno nuevo.
        self._queue = branch_queue if branch_queue is not None else BranchQueue()
        self._actions = {
            "1": self._issue_ticket,
            "2": self._call_next,
            "3": self._peek_next,
            "4": self._show_waiting,
            "5": self._show_stats,
        }

    def run(self) -> None:
        """Bucle principal: muestra el menú hasta que el usuario sale."""
        while True:
            print(self.MENU)
            choice = self._read("Elige una opción (1-6): ")

            # None = el usuario cerró la entrada (Ctrl+D / Ctrl+C).
            if choice is None or choice == self.EXIT_OPTION:
                print("Cerrando el gestor de turnos. ¡Hasta luego!")
                break

            action = self._actions.get(choice)
            if action is None:
                print("Opción no válida. Introduce un número del 1 al 6.")
                continue
            action()

    # --- Lectura segura de datos -----------------------------------------

    @staticmethod
    def _read(prompt: str) -> str | None:
        """Lee una línea sin espacios extra. Devuelve None si se interrumpe la entrada."""
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

    def _read_service(self) -> str | None:
        """Pide el servicio. Acepta el número o el nombre; Enter vacío cancela."""
        raw = self._read(self.SERVICE_PROMPT)
        if not raw:
            return None
        # Si escribe un atajo lo traducimos; si no, BranchQueue validará el texto.
        return self.SERVICE_SHORTCUTS.get(raw, raw)

    # --- Acciones del menú ------------------------------------------------

    def _issue_ticket(self) -> None:
        name = self._read("Nombre del cliente: ")
        if not name:
            print("El nombre no puede estar vacío. Operación cancelada.")
            return

        service = self._read_service()
        if service is None:
            print("Operación cancelada.")
            return

        try:
            ticket = self._queue.issue_ticket(name, service)
        except ValueError as error:  # incluye InvalidServiceTypeError
            print(error)
            return
        print(f"Ticket emitido: {ticket}")

    def _call_next(self) -> None:
        service = self._read_service()
        if service is None:
            print("Operación cancelada.")
            return
        try:
            ticket = self._queue.call_next(service)
        except (InvalidServiceTypeError, EmptyServiceQueueError) as error:
            print(error)
            return
        print(f"Llamando a: {ticket}")

    def _peek_next(self) -> None:
        service = self._read_service()
        if service is None:
            print("Operación cancelada.")
            return
        try:
            ticket = self._queue.peek_next(service)
        except (InvalidServiceTypeError, EmptyServiceQueueError) as error:
            print(error)
            return
        print(f"Siguiente en {SERVICE_LABELS[ticket.service_type]}: {ticket}")

    def _show_waiting(self) -> None:
        for service, tickets in self._queue.list_waiting().items():
            print(f"\n{SERVICE_LABELS[service]} ({len(tickets)} en espera):")
            if not tickets:
                print("  (sin clientes)")
            for position, ticket in enumerate(tickets, start=1):
                print(f"  {position}. {ticket}")

    def _show_stats(self) -> None:
        stats = self._queue.stats()
        print("Clientes en espera:")
        for service in SERVICE_TYPES:
            print(f"  {SERVICE_LABELS[service]}: {stats[service]}")
        print(f"  Total: {stats['total']}")


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def main() -> None:
    BranchCLI().run()


if __name__ == "__main__":
    main()