from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .db import connect, encode, initialize, utc_now


CapabilityHandler = Callable[[dict[str, Any], "ExecutionContext"], dict[str, Any]]
RollbackHandler = Callable[[dict[str, Any], "ExecutionContext"], dict[str, Any]]


@dataclass(frozen=True)
class ExecutionContext:
    data_dir: str
    actor: str
    dry_run: bool
    transaction_id: str
    operation_id: str


@dataclass(frozen=True)
class Capability:
    id: str
    name: str
    description: str
    domain: str
    handler: CapabilityHandler = field(repr=False, compare=False)
    input_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    output_schema: dict[str, Any] = field(default_factory=lambda: {"type": "object"})
    risk_level: str = "READ"
    cost_class: str = "LOW"
    permission_requirement: str = "READ"
    synchronous: bool = True
    supports_dry_run: bool = True
    supports_rollback: bool = False
    version: str = "1.0.0"
    rollback_handler: RollbackHandler | None = field(default=None, repr=False, compare=False)

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("handler", None)
        data.pop("rollback_handler", None)
        return data


class CapabilityRegistry:
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self._capabilities: dict[str, Capability] = {}
        initialize(data_dir)

    def register(self, capability: Capability) -> None:
        if not capability.id or capability.id in self._capabilities:
            raise ValueError(f"capability already registered or invalid: {capability.id}")
        self._capabilities[capability.id] = capability
        now = utc_now()
        with connect(self.data_dir) as connection:
            connection.execute(
                """
                INSERT INTO os_capabilities (
                    id, name, description, domain, input_schema_json, output_schema_json,
                    risk_level, cost_class, permission_requirement, synchronous,
                    supports_dry_run, supports_rollback, version, enabled, health, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'AVAILABLE', ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name, description=excluded.description, domain=excluded.domain,
                    input_schema_json=excluded.input_schema_json,
                    output_schema_json=excluded.output_schema_json,
                    risk_level=excluded.risk_level, cost_class=excluded.cost_class,
                    permission_requirement=excluded.permission_requirement,
                    synchronous=excluded.synchronous,
                    supports_dry_run=excluded.supports_dry_run,
                    supports_rollback=excluded.supports_rollback,
                    version=excluded.version, health='AVAILABLE', updated_at=excluded.updated_at
                """,
                (
                    capability.id, capability.name, capability.description, capability.domain,
                    encode(capability.input_schema), encode(capability.output_schema),
                    capability.risk_level, capability.cost_class,
                    capability.permission_requirement, int(capability.synchronous),
                    int(capability.supports_dry_run), int(capability.supports_rollback),
                    capability.version, now,
                ),
            )
            connection.commit()

    def get(self, capability_id: str) -> Capability:
        try:
            return self._capabilities[capability_id]
        except KeyError as exc:
            raise KeyError(f"capability_not_registered:{capability_id}") from exc

    def list(self, *, domain: str | None = None) -> list[dict[str, Any]]:
        capabilities = self._capabilities.values()
        if domain:
            capabilities = (item for item in capabilities if item.domain == domain)
        return [item.public_dict() for item in sorted(capabilities, key=lambda item: item.id)]

    def semantic_catalog(self) -> str:
        return "\n".join(
            f"- {item.id}: {item.description} [risk={item.risk_level}, permission={item.permission_requirement}]"
            for item in sorted(self._capabilities.values(), key=lambda item: item.id)
        )


def validate_input(schema: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if schema.get("type") == "object" and not isinstance(payload, dict):
        return ["input_must_be_object"]
    for key in schema.get("required", []):
        if key not in payload or payload[key] in (None, ""):
            errors.append(f"missing_required:{key}")
    properties = schema.get("properties", {})
    expected_types = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    for key, value in payload.items():
        declared = properties.get(key, {}) if isinstance(properties, dict) else {}
        expected = expected_types.get(declared.get("type"))
        if expected and not isinstance(value, expected):
            errors.append(f"invalid_type:{key}:{declared.get('type')}")
    return errors