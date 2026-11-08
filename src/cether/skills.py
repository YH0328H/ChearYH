"""Global skill enablement and declaration-driven tool registration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ToolDeclaration:
    """Describe a tool without installing or enabling its implementation."""

    name: str
    parameter_schema: dict[str, Any]
    return_type: str
    asynchronous: bool = False
    low_frequency: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("tool name must not be empty")
        if not isinstance(self.parameter_schema, dict) or self.parameter_schema.get("type") != "object":
            raise ValueError("parameter_schema must be an object schema")
        properties = self.parameter_schema.get("properties", {})
        required = self.parameter_schema.get("required", [])
        if not isinstance(properties, dict) or not isinstance(required, list) or not set(required).issubset(properties):
            raise ValueError("parameter_schema properties and required fields are invalid")
        if not self.return_type.strip():
            raise ValueError("return_type must not be empty")


@dataclass(frozen=True)
class RegisteredTool:
    declaration: ToolDeclaration
    handler: Callable[[dict[str, Any]], Any]


class SkillRegistry:
    """Keep global skill toggles separate from installed declarations.

    Tools are registered only while their global skill is enabled. The empty
    default registry enforces zero registration side effects at startup.
    """

    def __init__(self) -> None:
        self._enabled: dict[str, bool] = {}
        self._tools: dict[str, RegisteredTool] = {}
        self._declarations: dict[str, ToolDeclaration] = {}
        self._handlers: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self._owners: dict[str, str] = {}

    @property
    def tools(self) -> tuple[ToolDeclaration, ...]:
        return tuple(item.declaration for item in self._tools.values())

    def snapshot(self) -> dict[str, Any]:
        skills = sorted(set(self._enabled) | set(self._declarations))
        return {
            "skills": [
                {
                    "id": skill_id,
                    "installed": any(owner == skill_id for owner in self._owners.values()),
                    "enabled": self._enabled.get(skill_id, False),
                    "tools": sorted(
                        name for name in self._declarations
                        if self._owners[name] == skill_id and name in self._tools
                    ),
                }
                for skill_id in skills
            ],
            "tools": [
                {
                    "name": item.name,
                    "parameters": item.parameter_schema,
                    "returns": item.return_type,
                    "asynchronous": item.asynchronous,
                    "low_frequency": item.low_frequency,
                }
                for item in self.tools
            ],
        }

    def install(self, skill_id: str, declaration: ToolDeclaration,
                handler: Callable[[dict[str, Any]], Any]) -> None:
        if not skill_id.strip():
            raise ValueError("skill id must not be empty")
        if declaration.name in self._declarations:
            raise ValueError(f"tool already installed: {declaration.name}")
        self._declarations[declaration.name] = declaration
        self._handlers[declaration.name] = handler
        self._owners[declaration.name] = skill_id
        self._enabled.setdefault(skill_id, False)
        if self._enabled[skill_id]:
            self._tools[declaration.name] = RegisteredTool(declaration, handler)

    def set_enabled(self, skill_id: str, enabled: bool) -> dict[str, Any]:
        if not skill_id.strip():
            raise ValueError("skill id must not be empty")
        if type(enabled) is not bool:
            raise ValueError("enabled must be a boolean")
        self._enabled[skill_id] = enabled
        declarations = {name: declaration for name, declaration in self._declarations.items()
                        if self._skill_for(name) == skill_id}
        if enabled:
            self._tools.update({name: RegisteredTool(item, self._handlers[name])
                                for name, item in declarations.items()})
        else:
            for name in declarations:
                self._tools.pop(name, None)
        return self.snapshot()

    def _skill_for(self, tool_name: str) -> str | None:
        # Each declared tool's skill owner is recorded separately below.
        return self._owners.get(tool_name)

    def invoke(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        registered = self._tools.get(tool_name)
        if registered is None:
            raise KeyError(f"tool is not enabled: {tool_name}")
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")
        schema = registered.declaration.parameter_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if set(arguments) - set(properties) or set(required) - set(arguments):
            raise ValueError("tool arguments do not match the declared schema")
        for key, value in arguments.items():
            expected_type = properties[key].get("type") if isinstance(properties[key], dict) else None
            valid = {
                "string": lambda item: isinstance(item, str),
                "integer": lambda item: type(item) is int,
                "number": lambda item: type(item) in (int, float),
                "boolean": lambda item: type(item) is bool,
                "object": lambda item: isinstance(item, dict),
                "array": lambda item: isinstance(item, list),
            }.get(expected_type)
            if valid is None or not valid(value):
                raise ValueError(f"tool argument has invalid type: {key}")
        return registered.handler(arguments)

