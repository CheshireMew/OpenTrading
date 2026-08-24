from __future__ import annotations

import copy
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, get_args, get_origin

from fastapi.routing import APIRoute
from pydantic import BaseModel, TypeAdapter

REPO_ROOT = Path(__file__).resolve().parent.parent

from app.contracts.frontend import frontend_contract_filename, frontend_contract_target  # noqa: E402
from app.contracts.dto.errors import ApiErrorResponse  # noqa: E402
from app.main import create_app  # noqa: E402
from app.product import API_PREFIX  # noqa: E402
from app.domain.market.web3_chains import WEB3_ALL_CHAIN_ID, WEB3_CHAIN_CATALOG  # noqa: E402

FRONTEND_API_DIR = REPO_ROOT / "frontend" / "src" / "api"
TARGET_FILES = ("market.ts", "tools.ts", "config.ts")
TARGET_PATHS = {
    "market.ts": REPO_ROOT / "frontend" / "src" / "modules" / "market" / "generatedContracts.ts",
    "tools.ts": REPO_ROOT / "frontend" / "src" / "modules" / "tools" / "generatedContracts.ts",
    "config.ts": REPO_ROOT / "frontend" / "src" / "modules" / "system" / "generatedContracts.ts",
}
CONTRACT_APP = create_app("api")
TYPE_NAMESPACE_BY_FILE = {
    "market.ts": "MarketTypes",
    "tools.ts": "ToolsTypes",
    "config.ts": "ConfigTypes",
}


@dataclass(frozen=True)
class QueryParamContractField:
    name: str
    alias: str
    schema: dict[str, Any]
    required: bool


@dataclass(frozen=True)
class RouteContractModel:
    target_file: str
    model: type[BaseModel]


@dataclass(frozen=True)
class QueryParamContract:
    name: str
    target_file: str
    fields: tuple[QueryParamContractField, ...]
    route_name: str


def main() -> None:
    grouped_models: dict[str, list[type[BaseModel]]] = defaultdict(list)
    grouped_query_params: dict[str, list[QueryParamContract]] = defaultdict(list)
    for contract in collect_route_contract_models():
        grouped_models[contract.target_file].append(contract.model)
    for contract in collect_route_query_param_contracts():
        grouped_query_params[contract.target_file].append(contract)

    for filename in TARGET_FILES:
        content = render_file(
            grouped_models.get(filename, []),
            grouped_query_params.get(filename, []),
        )
        TARGET_PATHS[filename].write_text(content, encoding="utf-8")
    (FRONTEND_API_DIR / "routes.ts").write_text(render_api_routes(), encoding="utf-8")
    (FRONTEND_API_DIR / "errors.ts").write_text(render_file([ApiErrorResponse], []), encoding="utf-8")
    (TARGET_PATHS["market.ts"].parent / "generatedWeb3Chains.ts").write_text(
        render_web3_chain_catalog(),
        encoding="utf-8",
    )


def render_web3_chain_catalog() -> str:
    chains = [
        {"label": chain.label, "value": chain.chain_id}
        for chain in WEB3_CHAIN_CATALOG
    ]
    return "\n".join([
        "// This file is generated from app.domain.market.web3_chains.",
        "// Do not edit manually.",
        "",
        f"export const WEB3_ALL_CHAIN_ID = {json.dumps(WEB3_ALL_CHAIN_ID)}",
        f"export const WEB3_SUPPORTED_CHAIN_OPTIONS = {json.dumps(chains, ensure_ascii=False)} as const",
        "",
    ])


def collect_route_contract_models() -> tuple[RouteContractModel, ...]:
    models: dict[tuple[str, str], RouteContractModel] = {}
    for route in contract_routes():
        if not route.path.startswith(API_PREFIX):
            continue
        target_file = resolve_route_target_file(route)
        for model in extract_pydantic_models(route.response_model):
            models.setdefault((target_file, model.__name__), RouteContractModel(target_file, model))
        body_field = getattr(route, "body_field", None)
        if body_field is not None:
            for model in extract_pydantic_models(resolve_fastapi_field_annotation(body_field)):
                models.setdefault((target_file, model.__name__), RouteContractModel(target_file, model))
    if not models:
        raise RuntimeError("No FastAPI contract models were discovered")
    return tuple(models.values())


def collect_route_query_param_contracts() -> tuple[QueryParamContract, ...]:
    contracts: dict[str, QueryParamContract] = {}
    for route in contract_routes():
        if not route.path.startswith(API_PREFIX):
            continue
        if not route.dependant.query_params:
            continue
        interface_name = f"{pascal_case(route.name or 'route')}QueryParams"
        fields = tuple(
            QueryParamContractField(
                name=param.name,
                alias=getattr(param, "alias", param.name),
                schema=remap_schema(
                    TypeAdapter(resolve_fastapi_field_annotation(param)).json_schema(
                        ref_template="#/$defs/{model}"
                    )
                ),
                required=resolve_fastapi_field_required(param),
            )
            for param in route.dependant.query_params
        )
        contracts[interface_name] = QueryParamContract(
            name=interface_name,
            target_file=resolve_route_target_file(route),
            fields=fields,
            route_name=route.name,
        )
    return tuple(contracts.values())


def resolve_fastapi_field_annotation(field: Any) -> Any:
    for attr in ("type_", "annotation"):
        annotation = getattr(field, attr, None)
        if annotation is not None:
            return annotation
    field_info = getattr(field, "field_info", None)
    annotation = getattr(field_info, "annotation", None)
    if annotation is not None:
        return annotation
    raise TypeError(f"FastAPI field {getattr(field, 'name', '<unknown>')!r} does not expose a type annotation")


def resolve_fastapi_field_required(field: Any) -> bool:
    required = getattr(field, "required", None)
    if required is not None:
        return bool(required)
    is_required = getattr(field, "is_required", None)
    if callable(is_required):
        return bool(is_required())
    field_info = getattr(field, "field_info", None)
    field_info_is_required = getattr(field_info, "is_required", None)
    if callable(field_info_is_required):
        return bool(field_info_is_required())
    return False


def extract_pydantic_models(annotation: Any) -> tuple[type[BaseModel], ...]:
    if annotation is None:
        return ()
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return (annotation,)
    models: list[type[BaseModel]] = []
    for arg in get_args(annotation):
        models.extend(extract_pydantic_models(arg))
    return tuple(models)


def resolve_route_target_file(route: Any) -> str:
    return frontend_contract_filename(frontend_contract_target(route))


def render_api_routes() -> str:
    route_lines = [
        "// This file is generated from backend FastAPI route contracts.",
        "// Do not edit manually.",
        "",
        "import type * as MarketTypes from '../modules/market/contracts'",
        "import type * as ToolsTypes from '../modules/tools/contracts'",
        "import type * as ConfigTypes from '../modules/system/contracts'",
        "",
        "export type RouteParams = Record<string, string | number>",
        "export type ApiQueryShape = object",
        "export type EndpointQueryContract = { aliases?: Record<string, string>; repeatedKeys?: readonly string[] }",
        f"export const API_BASE_PATH = {json.dumps(API_PREFIX)}",
        "",
        "const fillRoute = (template: string, params: RouteParams = {}) => template.replace(/\\{([^}]+)\\}/g, (_, key: string) => {",
        "  const value = params[key]",
        "  if (value === undefined || value === null || value === '') throw new Error(`Missing API route param: ${key}`)",
        "  return encodeURIComponent(String(value))",
        "})",
        "",
        "const routeTemplates = {",
    ]
    query_meta: dict[str, dict[str, Any]] = {}
    query_types: dict[str, str] = {}
    for contract in collect_route_query_param_contracts():
        query_meta[contract.route_name] = query_meta_payload(contract)
        query_types[contract.route_name] = qualified_type_name(contract.target_file, contract.name)
    route_query_lines = ["const endpointQueryContracts = {"]
    response_map_lines = ["export type ApiRouteResponseMap = {"]
    body_map_lines = ["export type ApiRouteBodyMap = {"]
    query_map_lines = ["export type ApiRouteQueryMap = {"]
    path_map_lines = ["export type ApiRoutePathMap = {"]
    for route in sorted(api_v1_routes(), key=lambda item: item.name):
        route_lines.append(f"  {route.name}: {json.dumps(strip_api_prefix(route.path))},")
        route_query_lines.append(
            f"  {route.name}: {json.dumps(query_meta.get(route.name, empty_query_meta()), ensure_ascii=False)} as EndpointQueryContract,"
        )
        target_file = resolve_route_target_file(route)
        response_map_lines.append(
            f"  {route.name}: {render_route_annotation_type(route.response_model, target_file)}"
        )
        body_field = getattr(route, "body_field", None)
        body_annotation = resolve_fastapi_field_annotation(body_field) if body_field is not None else None
        body_map_lines.append(
            f"  {route.name}: {render_route_annotation_type(body_annotation, target_file, fallback='never')}"
        )
        query_map_lines.append(
            f"  {route.name}: {query_types.get(route.name, 'never')}"
        )
        path_names = re.findall(r"\{([^}:]+)(?::[^}]+)?\}", route.path)
        path_type = (
            "{ " + "; ".join(f"{name}: string | number" for name in path_names) + " }"
            if path_names
            else "never"
        )
        path_map_lines.append(f"  {route.name}: {path_type}")
    route_lines.extend([
        "} as const",
        "",
        "export type ApiRouteName = keyof typeof routeTemplates",
        "",
        "export const apiRoute = (name: ApiRouteName, params?: RouteParams) => fillRoute(routeTemplates[name], params)",
        "",
        "export const apiEndpoint = (name: ApiRouteName, params?: RouteParams) => ({",
        "  name,",
        "  url: apiRoute(name, params),",
        "  query: endpointQueryContracts[name],",
        "})",
        "",
        "export const serializeEndpointQuery = (name: ApiRouteName, params: ApiQueryShape = {}) => {",
        "  const contract = endpointQueryContracts[name]",
        "  const query = new URLSearchParams()",
        "  Object.entries(params as Record<string, unknown>).forEach(([key, value]) => {",
        "    if (value === null || value === undefined || value === '') return",
        "    const resolvedKey = contract?.aliases?.[key] ?? key",
        "    const repeatedKeys = contract?.repeatedKeys ?? []",
        "    if (Array.isArray(value)) {",
        "      value.forEach((item) => {",
        "        if (item !== null && item !== undefined && item !== '') query.append(resolvedKey, String(item))",
        "      })",
        "      return",
        "    }",
        "    if (repeatedKeys.includes(key)) {",
        "      query.append(resolvedKey, String(value))",
        "      return",
        "    }",
        "    query.set(resolvedKey, String(value))",
        "  })",
        "  return query.toString()",
        "}",
        "",
    ])
    route_query_lines.extend(["} as const", ""])
    response_map_lines.extend(["}", ""])
    body_map_lines.extend(["}", ""])
    path_map_lines.extend(["}", ""])
    query_map_lines.extend([
        "}",
        "",
        "export type ApiRouteResponse<N extends ApiRouteName> = ApiRouteResponseMap[N]",
        "export type ApiRouteBody<N extends ApiRouteName> = ApiRouteBodyMap[N]",
        "export type ApiRouteQuery<N extends ApiRouteName> = ApiRouteQueryMap[N]",
        "export type ApiRoutePath<N extends ApiRouteName> = ApiRoutePathMap[N]",
        "",
    ])
    return "\n".join(
        route_lines
        + route_query_lines
        + response_map_lines
        + body_map_lines
        + path_map_lines
        + query_map_lines
    )


def contract_routes() -> tuple[Any, ...]:
    """Return resolved HTTP routes across eager and deferred FastAPI routers."""
    routes: list[Any] = []
    for route in CONTRACT_APP.routes:
        if isinstance(route, APIRoute):
            routes.append(route)
            continue
        effective_contexts = getattr(route, "effective_route_contexts", None)
        if not callable(effective_contexts):
            continue
        for context in effective_contexts():
            if isinstance(getattr(context, "original_route", None), APIRoute):
                routes.append(context)
    return tuple(routes)


def api_v1_routes() -> tuple[Any, ...]:
    return tuple(
        route
        for route in contract_routes()
        if route.path.startswith(API_PREFIX)
    )


def strip_api_prefix(path: str) -> str:
    if not path.startswith(API_PREFIX):
        return path
    return path[len(API_PREFIX):] or "/"


def empty_query_meta() -> dict[str, Any]:
    return {"repeatedKeys": [], "aliases": {}}


def qualified_type_name(target_file: str, name: str) -> str:
    namespace = TYPE_NAMESPACE_BY_FILE[target_file]
    return f"{namespace}.{name}"


def render_route_annotation_type(annotation: Any, target_file: str, *, fallback: str = "unknown") -> str:
    if annotation is None:
        return fallback
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return qualified_type_name(target_file, annotation.__name__)
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in {list, tuple} and args:
        return f"Array<{render_route_annotation_type(args[0], target_file, fallback=fallback)}>"
    if origin is dict and len(args) == 2:
        key_type = render_plain_ts_type(args[0])
        value_type = render_route_annotation_type(args[1], target_file, fallback="unknown")
        return f"Record<{key_type}, {value_type}>"
    if args:
        rendered = [
            render_route_annotation_type(arg, target_file, fallback=fallback)
            for arg in args
            if arg is not type(None)
        ]
        return " | ".join(dict.fromkeys(rendered)) or fallback
    return render_plain_ts_type(annotation, fallback=fallback)


def render_plain_ts_type(annotation: Any, *, fallback: str = "unknown") -> str:
    if annotation is str:
        return "string"
    if annotation in {int, float}:
        return "number"
    if annotation is bool:
        return "boolean"
    if annotation is Any:
        return "unknown"
    return fallback


def query_meta_payload(contract: QueryParamContract) -> dict[str, Any]:
    return {
        "repeatedKeys": [
            field.name
            for field in contract.fields
            if schema_contains_array(field.schema)
        ],
        "aliases": {
            field.name: field.alias
            for field in contract.fields
            if field.alias != field.name
        },
    }


def render_file(
    models: list[type[BaseModel]],
    query_contracts: list[QueryParamContract],
) -> str:
    definitions: dict[str, dict[str, Any]] = {}
    root_names: list[str] = []
    for model in models:
        name = model.__name__
        schema = copy.deepcopy(model.model_json_schema(ref_template="#/$defs/{model}"))
        schema = remap_schema(schema)
        definitions[name] = strip_defs(schema)
        root_names.append(name)
        for def_name, def_schema in schema.get("$defs", {}).items():
            normalized_def_schema = strip_defs(def_schema)
            if def_name not in definitions or is_self_reference_schema(definitions[def_name], def_name):
                definitions[def_name] = normalized_def_schema

    lines = [
        "// This file is generated from backend FastAPI route contracts.",
        "// Do not edit manually.",
        "",
    ]

    emitted: set[str] = set()
    for name in root_names + sorted(definitions.keys()):
        if name in emitted:
            continue
        lines.extend(emit_named_definition(name, definitions[name]))
        lines.append("")
        emitted.add(name)

    for contract in sorted(query_contracts, key=lambda item: item.name):
        lines.extend(emit_query_contract(contract))
        lines.append("")

    return "\n".join(lines)


def remap_schema(value: Any) -> Any:
    if isinstance(value, dict):
        remapped: dict[str, Any] = {}
        for key, item in value.items():
            if key == "$defs":
                remapped[key] = {def_name: remap_schema(def_schema) for def_name, def_schema in item.items()}
                continue
            if key == "$ref" and isinstance(item, str):
                remapped[key] = f"#/$defs/{item.split('/')[-1]}"
                continue
            remapped[key] = remap_schema(item)
        return remapped
    if isinstance(value, list):
        return [remap_schema(item) for item in value]
    return value


def strip_defs(schema: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(schema)
    result.pop("$defs", None)
    result.pop("title", None)
    return result


def is_self_reference_schema(schema: dict[str, Any], name: str) -> bool:
    return isinstance(schema, dict) and schema.get("$ref") == f"#/$defs/{name}"


def emit_named_definition(name: str, schema: dict[str, Any]) -> list[str]:
    if is_object_schema(schema):
        return emit_interface(name, schema)
    return [f"export type {name} = {render_type(schema)}"]


def emit_interface(name: str, schema: dict[str, Any]) -> list[str]:
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))
    lines = [f"export interface {name} {{"]
    for prop_name, prop_schema in properties.items():
        optional = "?" if prop_name not in required and "const" not in prop_schema else ""
        lines.append(f"  {prop_name}{optional}: {render_type(prop_schema)}")
    if schema.get("additionalProperties"):
        lines.append(f"  [key: string]: {render_type(schema['additionalProperties'])}")
    lines.append("}")
    return lines


def emit_query_contract(contract: QueryParamContract) -> list[str]:
    lines = [f"export interface {contract.name} {{"]
    for field in contract.fields:
        optional = "?" if not field.required else ""
        lines.append(f"  {field.name}{optional}: {render_type(field.schema)}")
    lines.append("}")
    return lines


def render_type(schema: dict[str, Any]) -> str:
    if schema is True:
        return "unknown"
    if schema is False:
        return "never"
    if not isinstance(schema, dict):
        return "unknown"
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    if "anyOf" in schema:
        return " | ".join(dict.fromkeys(render_type(item) for item in schema["anyOf"]))
    if "oneOf" in schema:
        return " | ".join(dict.fromkeys(render_type(item) for item in schema["oneOf"]))
    if "allOf" in schema:
        return " & ".join(dict.fromkeys(render_type(item) for item in schema["allOf"]))
    if "enum" in schema:
        return " | ".join(json.dumps(item) for item in schema["enum"])
    if "const" in schema:
        return json.dumps(schema["const"])
    if schema.get("type") == "array":
        return f"Array<{render_type(schema.get('items', {}))}>"
    if is_object_schema(schema):
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        members = []
        for prop_name, prop_schema in properties.items():
            optional = "?" if prop_name not in required else ""
            members.append(f"{prop_name}{optional}: {render_type(prop_schema)}")
        if schema.get("additionalProperties"):
            members.append(f"[key: string]: {render_type(schema['additionalProperties'])}")
        return "{ " + "; ".join(members) + " }"
    if schema.get("additionalProperties") is True:
        return "Record<string, unknown>"
    if schema.get("additionalProperties") is not None:
        return f"Record<string, {render_type(schema['additionalProperties'])}>"
    schema_type = schema.get("type")
    if schema_type in {"integer", "number"}:
        return "number"
    if schema_type == "string":
        return "string"
    if schema_type == "boolean":
        return "boolean"
    if schema_type == "null":
        return "null"
    return "unknown"


def is_object_schema(schema: dict[str, Any]) -> bool:
    return schema.get("type") == "object" or "properties" in schema


def schema_contains_array(schema: dict[str, Any]) -> bool:
    if schema.get("type") == "array":
        return True
    for key in ("anyOf", "oneOf", "allOf"):
        if any(schema_contains_array(item) for item in schema.get(key, [])):
            return True
    return False


def pascal_case(value: str) -> str:
    tokens: list[str] = []
    current = ""
    for char in value:
        if char.isalnum():
            current += char
            continue
        if current:
            tokens.append(current)
            current = ""
    if current:
        tokens.append(current)
    return "".join(token[:1].upper() + token[1:] for token in tokens if token)

if __name__ == "__main__":
    main()
