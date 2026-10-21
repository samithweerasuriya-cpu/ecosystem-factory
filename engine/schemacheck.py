"""Minimal JSON Schema checker (stdlib only), so engine scripts never depend on the venv.

Implements the keywords the engine's schemas use: type, enum, const, required, properties,
additionalProperties, items, minItems, contains, pattern, minLength, minimum, maximum,
allOf, anyOf, oneOf, if/then, and local $ref ("#/$defs/<name>"). Derived from the
validator in the author's earlier private lab. Tests cross-check it against the
`jsonschema` package where that is installed.
"""
import re

TYPES = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def type_ok(value, t):
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, TYPES[t])


def resolve(schema, root):
    ref = schema.get("$ref")
    if not ref:
        return schema
    if not ref.startswith("#/$defs/"):
        raise ValueError(f"unsupported $ref {ref!r}")
    return root["$defs"][ref[len("#/$defs/"):]]


def check(value, schema, path="$", root=None):
    """Return a list of 'path: message' errors for value against schema."""
    root = schema if root is None else root
    schema = resolve(schema, root)
    errs = []
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(type_ok(value, t) for t in types):
            return [f"{path}: expected {'/'.join(types)}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errs.append(f"{path}: {value!r} not one of {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errs.append(f"{path}: must be {schema['const']!r}, got {value!r}")
    if isinstance(value, str):
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errs.append(f"{path}: {value!r} does not match {schema['pattern']!r}")
        if len(value) < schema.get("minLength", 0):
            errs.append(f"{path}: shorter than {schema['minLength']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errs.append(f"{path}: {value} is below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errs.append(f"{path}: {value} is above {schema['maximum']}")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errs.append(f"{path}: missing required field '{key}'")
        props = schema.get("properties", {})
        for key, sub in props.items():
            if key in value:
                errs += check(value[key], sub, f"{path}.{key}", root)
        extra = schema.get("additionalProperties", True)
        for key in value:
            if key in props:
                continue
            if extra is False:
                errs.append(f"{path}: unexpected field '{key}'")
            elif isinstance(extra, dict):
                errs += check(value[key], extra, f"{path}.{key}", root)
    if isinstance(value, list):
        if "items" in schema:
            for i, item in enumerate(value):
                errs += check(item, schema["items"], f"{path}[{i}]", root)
        if len(value) < schema.get("minItems", 0):
            errs.append(f"{path}: needs at least {schema['minItems']} item(s)")
        if "contains" in schema and not any(not check(item, schema["contains"], path, root) for item in value):
            errs.append(f"{path}: no item matches the required 'contains' schema")
    for sub in schema.get("allOf", []):
        errs += check(value, sub, path, root)
    if "anyOf" in schema and all(check(value, sub, path, root) for sub in schema["anyOf"]):
        errs.append(f"{path}: matches none of the allowed forms")
    if "oneOf" in schema:
        n = sum(1 for sub in schema["oneOf"] if not check(value, sub, path, root))
        if n != 1:
            errs.append(f"{path}: must match exactly one allowed form (matched {n})")
    if "if" in schema and not check(value, schema["if"], path, root):
        errs += check(value, schema.get("then", {}), path, root)
    return errs
