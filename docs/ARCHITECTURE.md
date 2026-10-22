# OpenTrading architecture boundaries

OpenTrading uses a small inward-facing core and an explicit outer runtime shell.

`app/domain` owns business values and rules. It cannot import HTTP contracts, runtime services, infrastructure, or routers. `app/application` owns use cases, ports, and application errors. It can depend on the domain, but not on contracts, infrastructure, services, routers, or FastAPI.

`app/services` is deliberately the outer orchestration layer, not the application core. It adapts transport commands, schedules blocking work on the named executors, coordinates external clients, and returns transport-ready results. Its ability to use `app/contracts` and `app/infra` is intentional; inner layers must never import it.

`app/infra` implements application ports and owns databases, caches, executors, and external clients. It may depend on `app/application` and `app/domain`, but never on transport contracts, routers, service orchestration, or application-wide HTTP exceptions. Infrastructure reports domain or application errors; `app/main.py` maps those errors to the single HTTP error contract.

`app/contracts` and `app/routers` form the HTTP boundary. Generated frontend types and route maps come only from these FastAPI routes. `app/runtime.py` is the composition root that wires concrete outer adapters to inner ports.
