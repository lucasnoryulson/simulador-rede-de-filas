#!/usr/bin/env python3
"""Simulação de redes de filas por eventos discretos, com entrada em YAML."""

from __future__ import annotations

import argparse
import heapq
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Falta instalar o PyYAML. Execute: pip install -r requirements.txt"
    ) from exc


class ParametersLoader(yaml.SafeLoader):
    """Aceita a tag !PARAMETERS dos modelos da disciplina."""


def _parameters_constructor(loader: ParametersLoader, node: yaml.Node):
    return loader.construct_mapping(node, deep=True)


ParametersLoader.add_constructor("!PARAMETERS", _parameters_constructor)


class RandomExhausted(RuntimeError):
    pass


class NumberSampler:
    def has_next(self) -> bool:
        raise NotImplementedError

    def next(self) -> float:
        raise NotImplementedError

    @property
    def consumed(self) -> int:
        raise NotImplementedError


class ListSampler(NumberSampler):
    def __init__(self, values: Iterable[float]):
        self.values = list(values)
        self.index = 0

    def has_next(self) -> bool:
        return self.index < len(self.values)

    def next(self) -> float:
        if not self.has_next():
            raise RandomExhausted("Acabaram os números aleatórios")
        value = float(self.values[self.index])
        self.index += 1
        return value

    @property
    def consumed(self) -> int:
        return self.index


class LinearCongruentialSampler(NumberSampler):
    """Gerador congruente linear com os parâmetros do simulator.jar."""

    A = 25214903917
    C = 11
    M = 281474976710656  # 2**48

    def __init__(self, limit: int, seed: int):
        self.limit = int(limit)
        self.x = int(seed)
        self.count = 0

    def has_next(self) -> bool:
        return self.count < self.limit

    def next(self) -> float:
        if not self.has_next():
            raise RandomExhausted("Acabaram os números aleatórios")
        self.x = (self.A * self.x + self.C) % self.M
        self.count += 1
        return self.x / self.M

    @property
    def consumed(self) -> int:
        return self.count


@dataclass
class Route:
    probability: float
    target: "Queue"


@dataclass
class Queue:
    id: str
    servers: int
    capacity: int = -1
    min_arrival: float = -1.0
    max_arrival: float = -1.0
    min_service: float = -1.0
    max_service: float = -1.0
    population: int = 0
    losses: int = 0
    state_times: Dict[int, float] = field(default_factory=dict)
    routes: List[Route] = field(default_factory=list)
    env: Optional["Environment"] = field(default=None, repr=False)

    def choose_destination(self) -> Optional["Queue"]:
        # Uma rota com 100% de chance dispensa sorteio, como no JAR.
        if not self.routes:
            return None
        if len(self.routes) == 1 and self.routes[0].probability >= 1.0:
            return self.routes[0].target

        assert self.env is not None
        remaining = self.env.random_next()
        for route in self.routes:
            if remaining <= route.probability:
                return route.target
            remaining -= route.probability
        # Se nenhuma rota foi escolhida, o cliente sai da rede.
        return None

    def arrival(self, external: bool) -> None:
        assert self.env is not None
        self.env.account_time()

        has_capacity = self.capacity < 0 or self.population < self.capacity
        if has_capacity:
            self.population += 1
            if self.population <= self.servers:
                # Sorteia o destino antes do tempo de atendimento, como no JAR.
                destination = self.choose_destination()
                self.env.schedule_departure(self, destination)
        else:
            self.losses += 1

        if external:
            self.env.schedule_arrival(self)

    def departure(self) -> None:
        assert self.env is not None
        self.env.account_time()
        self.population -= 1
        if self.population >= self.servers:
            destination = self.choose_destination()
            self.env.schedule_departure(self, destination)


@dataclass(order=True)
class Event:
    time: float
    sequence: int
    kind: str = field(compare=False)
    queue: Queue = field(compare=False)
    destination: Optional[Queue] = field(default=None, compare=False)


class Environment:
    def __init__(self, queues: Dict[str, Queue]):
        self.queues = queues
        for queue in queues.values():
            queue.env = self
        self.events: List[Event] = []
        self.initial_events: List[Tuple[str, float]] = []
        self.sampler: Optional[NumberSampler] = None
        self.time = 0.0
        self.last_event = 0.0
        self.accumulated_time = 0.0
        self._sequence = 0
        self.randoms_consumed_per_run: List[int] = []

    def random_next(self) -> float:
        if self.sampler is None:
            raise RuntimeError("Gerador de números aleatórios não configurado")
        return self.sampler.next()

    def random_uniform(self, minimum: float, maximum: float) -> float:
        return minimum + (maximum - minimum) * self.random_next()

    def _push_event(
        self,
        time: float,
        kind: str,
        queue: Queue,
        destination: Optional[Queue] = None,
    ) -> Event:
        self._sequence += 1
        event = Event(time, self._sequence, kind, queue, destination)
        heapq.heappush(self.events, event)
        return event

    def add_initial_arrival(self, queue: Queue, at_time: float) -> None:
        self.initial_events.append((queue.id, float(at_time)))
        self._push_event(float(at_time), "arrival", queue)

    def schedule_arrival(self, queue: Queue) -> None:
        delta = self.random_uniform(queue.min_arrival, queue.max_arrival)
        self._push_event(self.time + delta, "arrival", queue)

    def schedule_departure(self, queue: Queue, destination: Optional[Queue]) -> None:
        delta = self.random_uniform(queue.min_service, queue.max_service)
        self._push_event(self.time + delta, "departure", queue, destination)

    def account_time(self) -> None:
        delta = self.time - self.last_event
        for queue in self.queues.values():
            state = queue.population
            queue.state_times[state] = queue.state_times.get(state, 0.0) + delta
        self.last_event = self.time

    def step(self) -> None:
        if not self.events:
            raise StopIteration

        event = heapq.heappop(self.events)
        self.last_event = self.time
        self.time = event.time

        if event.kind == "arrival":
            event.queue.arrival(external=True)
        elif event.kind == "departure":
            event.queue.departure()
            if event.destination is not None:
                event.destination.arrival(external=False)
        else:  # pragma: no cover
            raise RuntimeError(f"Tipo de evento desconhecido: {event.kind}")

    def reset_for_next_run(self) -> None:
        if self.sampler is not None:
            self.randoms_consumed_per_run.append(self.sampler.consumed)
        self.events.clear()
        self.accumulated_time += self.time
        self.time = 0.0
        self.last_event = 0.0
        for queue in self.queues.values():
            queue.population = 0
        for queue_id, at_time in self.initial_events:
            self._push_event(at_time, "arrival", self.queues[queue_id])

    @property
    def total_time(self) -> float:
        return self.time + self.accumulated_time


@dataclass
class SimulationConfig:
    arrivals: Dict[str, float]
    queues: Dict[str, dict]
    network: List[dict]
    rndnumbers: List[float]
    seeds: List[int]
    rndnumbers_per_seed: int


def load_config(path: Path) -> SimulationConfig:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.load(handle, Loader=ParametersLoader)

    if not isinstance(data, dict):
        raise ValueError("O arquivo YAML deve conter um mapa de parâmetros")

    return SimulationConfig(
        arrivals={str(k): float(v) for k, v in (data.get("arrivals") or {}).items()},
        queues=dict(data.get("queues") or {}),
        network=list(data.get("network") or []),
        rndnumbers=[float(x) for x in (data.get("rndnumbers") or [])],
        seeds=[int(x) for x in (data.get("seeds") or [])],
        rndnumbers_per_seed=int(data.get("rndnumbersPerSeed", 100000)),
    )


def validate_config(config: SimulationConfig) -> None:
    if not config.queues:
        raise ValueError("Nenhuma fila foi definida em 'queues'")

    for qid, raw in config.queues.items():
        servers = int(raw.get("servers", -1))
        capacity = int(raw.get("capacity", -1))
        min_service = float(raw.get("minService", -1.0))
        max_service = float(raw.get("maxService", -1.0))
        if servers <= 0:
            raise ValueError(f"Fila {qid}: 'servers' deve ser > 0")
        if capacity != -1 and capacity < servers:
            raise ValueError(
                f"Fila {qid}: 'capacity' deve ser >= servers ou ser omitida"
            )
        if min_service < 0 or max_service < min_service:
            raise ValueError(f"Fila {qid}: intervalo de atendimento inválido")

    for qid, first_arrival in config.arrivals.items():
        if qid not in config.queues:
            raise ValueError(f"Fila de chegada externa não encontrada: {qid}")
        raw = config.queues[qid]
        amin = float(raw.get("minArrival", -1.0))
        amax = float(raw.get("maxArrival", -1.0))
        if first_arrival < 0:
            raise ValueError(f"Fila {qid}: primeira chegada deve ser >= 0")
        if amin < 0 or amax < amin:
            raise ValueError(f"Fila {qid}: intervalo entre chegadas inválido")

    route_sums: Dict[str, float] = {}
    for edge in config.network:
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        probability = float(edge.get("probability", -1.0))
        if source not in config.queues:
            raise ValueError(f"Fila de origem não encontrada: {source}")
        if target not in config.queues:
            raise ValueError(f"Fila de destino não encontrada: {target}")
        if probability < 0 or probability > 1:
            raise ValueError(
                f"Rota {source}->{target}: probability deve estar entre 0 e 1"
            )
        route_sums[source] = route_sums.get(source, 0.0) + probability

    for source, total in route_sums.items():
        if total > 1.0 + 1e-12:
            raise ValueError(
                f"Soma das probabilidades de saída de {source} = {total:.6f} (> 1)"
            )

    if config.seeds:
        if config.rndnumbers_per_seed <= 0:
            raise ValueError("rndnumbersPerSeed deve ser > 0")
    elif not config.rndnumbers:
        raise ValueError("Informe 'seeds' ou uma lista em 'rndnumbers'")


def build_environment(config: SimulationConfig) -> Environment:
    queues: Dict[str, Queue] = {}
    for qid, raw in config.queues.items():
        queues[str(qid)] = Queue(
            id=str(qid),
            servers=int(raw.get("servers", -1)),
            capacity=int(raw.get("capacity", -1)),
            min_arrival=float(raw.get("minArrival", -1.0)),
            max_arrival=float(raw.get("maxArrival", -1.0)),
            min_service=float(raw.get("minService", -1.0)),
            max_service=float(raw.get("maxService", -1.0)),
        )

    env = Environment(queues)

    for edge in config.network:
        source = queues[str(edge["source"])]
        target = queues[str(edge["target"])]
        source.routes.append(Route(float(edge["probability"]), target))

    # Mantém a ordem de sorteio das rotas usada pelo JAR.
    for queue in queues.values():
        queue.routes.sort(key=lambda route: route.probability)

    for qid, at_time in config.arrivals.items():
        env.add_initial_arrival(queues[qid], at_time)

    return env


def run_simulation(config: SimulationConfig) -> Tuple[Environment, int]:
    validate_config(config)
    env = build_environment(config)

    if config.seeds:
        runs = len(config.seeds)
        for seed in config.seeds:
            env.sampler = LinearCongruentialSampler(config.rndnumbers_per_seed, seed)
            try:
                while env.sampler.has_next():
                    env.step()
            except (RandomExhausted, StopIteration):
                pass
            env.reset_for_next_run()
    else:
        runs = 1
        env.sampler = ListSampler(config.rndnumbers)
        try:
            while env.sampler.has_next():
                env.step()
        except (RandomExhausted, StopIteration):
            pass
        env.reset_for_next_run()

    return env, runs


def format_report(env: Environment, runs: int) -> str:
    lines = ["Resultado da simulação", ""]
    total_time = env.total_time

    for qid in sorted(env.queues):
        queue = env.queues[qid]
        model = f"G/G/{queue.servers}"
        if queue.capacity >= 0:
            model += f"/{queue.capacity}"
        lines.append(f"{queue.id} ({model})")
        if queue.min_arrival != -1.0:
            lines.append(
                f"Intervalo entre chegadas: {queue.min_arrival:.1f} a {queue.max_arrival:.1f}"
            )
        lines.append(f"Atendimento: {queue.min_service:.1f} a {queue.max_service:.1f}")
        lines.append(f"{'Clientes':>8} {'Tempo no estado':>18} {'Probabilidade':>16}")
        for state in sorted(queue.state_times):
            state_time = queue.state_times[state]
            probability = (state_time / total_time * 100.0) if total_time else 0.0
            lines.append(f"{state:8d} {state_time:18.4f} {probability:15.2f}%")
        lines.extend([f"Clientes perdidos: {queue.losses}", ""])

    average = total_time / runs if runs else math.nan
    lines.append(f"Tempo total: {total_time:.4f}")
    if runs > 1:
        lines.append(f"Tempo médio por execução: {average:.4f}")
    if env.randoms_consumed_per_run:
        consumed = ", ".join(str(x) for x in env.randoms_consumed_per_run)
        label = "Números aleatórios consumidos"
        if runs > 1:
            label += " por execução"
        lines.append(f"{label}: {consumed}")
    return "\n".join(lines)


EXAMPLE_YAML = """# Exemplo com duas filas; 70% dos clientes de Q1 seguem para Q2.
!PARAMETERS
arrivals:
   Q1: 2.0

queues:
   Q1:
      servers: 1
      minArrival: 2.0
      maxArrival: 4.0
      minService: 1.0
      maxService: 2.0
   Q2:
      servers: 2
      capacity: 5
      minService: 4.0
      maxService: 8.0

network:
-  source: Q1
   target: Q2
   probability: 0.7

rndnumbersPerSeed: 100000
seeds:
- 1
"""


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Simulador de redes de filas"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Executa um modelo YAML")
    run_parser.add_argument("model", type=Path, help="Arquivo .yml do modelo")
    run_parser.add_argument(
        "--output", "-o", type=Path, help="Salva também o relatório em arquivo"
    )

    example_parser = sub.add_parser("example", help="Cria um model.yml de exemplo")
    example_parser.add_argument(
        "--output", "-o", type=Path, default=Path("model.yml")
    )

    args = parser.parse_args(argv)

    if args.command == "example":
        args.output.write_text(EXAMPLE_YAML, encoding="utf-8")
        print(f"Arquivo de exemplo criado: {args.output}")
        return 0

    try:
        config = load_config(args.model)
        env, runs = run_simulation(config)
        report = format_report(env, runs)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    print(report)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
