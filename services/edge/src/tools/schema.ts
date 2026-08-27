import * as v from "valibot";

// The tool catalogue is declared as JSON Schema, in Python, where the tools
// themselves live; Flue validates model arguments with Valibot before it calls
// anything. So one translation has to exist, and this is it -- the alternative
// is duplicating every tool's argument shape in TypeScript and letting the two
// drift.
//
// Deliberately partial: the subset arch's tool declarations actually use
// (objects, primitives, enums, arrays, nesting). An unrecognised construct
// becomes v.unknown() -- permissive here rather than rejecting a call the far
// side would have accepted, because the far side validates too and it is the one
// that owns the signature.

type Json = Record<string, unknown>;

// Both sides of the schema are the argument bag: what the model sends and what
// `run` receives are the same shape, and saying so is what gives `data` a type
// instead of `unknown`.
export type ToolArgsSchema = v.GenericSchema<Record<string, unknown>, Record<string, unknown>>;

export function toolInput(parameters: Json): ToolArgsSchema {
  const entries = propertiesOf(parameters);
  if (entries === undefined) {
    // A tool that declares no properties takes a free-form bag rather than
    // nothing: rejecting arguments the far side would accept is the one failure
    // mode this translation must not introduce.
    return v.record(v.string(), v.unknown()) as unknown as ToolArgsSchema;
  }
  return v.object(entries) as unknown as ToolArgsSchema;
}

function propertiesOf(schema: Json): Record<string, v.GenericSchema> | undefined {
  const properties = schema["properties"];
  if (typeof properties !== "object" || properties === null) return undefined;

  const required = new Set(
    Array.isArray(schema["required"]) ? schema["required"].filter((n): n is string => typeof n === "string") : [],
  );

  const entries: Record<string, v.GenericSchema> = {};
  for (const [name, declared] of Object.entries(properties as Json)) {
    const leaf = schemaOf(declared);
    // An optional argument the model omits must not fail validation, and its
    // absence must reach the far side as absence rather than as null.
    entries[name] = required.has(name) ? leaf : (v.optional(leaf) as unknown as v.GenericSchema);
  }
  return entries;
}

function schemaOf(declared: unknown): v.GenericSchema {
  if (typeof declared !== "object" || declared === null) return v.unknown();
  const node = declared as Json;

  const options = node["enum"];
  if (Array.isArray(options) && options.every((option): option is string => typeof option === "string")) {
    return v.picklist(options) as unknown as v.GenericSchema;
  }

  switch (node["type"]) {
    case "string":
      return v.string() as unknown as v.GenericSchema;
    case "number":
      return v.number() as unknown as v.GenericSchema;
    case "integer":
      return v.pipe(v.number(), v.integer()) as unknown as v.GenericSchema;
    case "boolean":
      return v.boolean() as unknown as v.GenericSchema;
    case "array":
      return v.array(schemaOf(node["items"])) as unknown as v.GenericSchema;
    case "object": {
      const entries = propertiesOf(node);
      return (
        entries === undefined ? v.record(v.string(), v.unknown()) : v.object(entries)
      ) as unknown as v.GenericSchema;
    }
    default:
      return v.unknown();
  }
}
