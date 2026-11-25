import { ApiRequestError } from '@/api/request'

/** The subset emitted by our Pydantic command models, with their generated
 * constraints/defaults. Cross-record rules remain inside storage transactions. */
export function validateSchema(value: unknown, schema: any, root = schema, path = 'record'): any {
  const invalid = (): never => { throw new ApiRequestError('Invalid research record: ' + path, { status: 422 }) }
  if (schema === true) return value
  if (schema === false) return invalid()
  if (schema.$ref) return validateSchema(value, schema.$ref.slice(2).split('/').reduce((node: any, key: string) => node[key.replace(/~1/g, '/').replace(/~0/g, '~')], root), root, path)
  if (value === undefined && 'default' in schema) value = structuredClone(schema.default)
  if (schema.anyOf) {
    for (const option of schema.anyOf) { try { return validateSchema(value, option, root, path) } catch { /* Try the next supported type. */ } }
    return invalid()
  }
  if ('const' in schema && value !== schema.const || schema.enum && !schema.enum.includes(value)) return invalid()
  if (schema.type === 'null') { if (value !== null) invalid(); return null }
  if (schema.type === 'boolean') { if (typeof value !== 'boolean') invalid(); return value }
  if (schema.type === 'number' || schema.type === 'integer') {
    if (typeof value !== 'number' || !Number.isFinite(value) || schema.type === 'integer' && !Number.isInteger(value)) return invalid()
    if (schema.minimum !== undefined && value < schema.minimum || schema.maximum !== undefined && value > schema.maximum
      || schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum || schema.exclusiveMaximum !== undefined && value >= schema.exclusiveMaximum) return invalid()
    return value
  }
  if (schema.type === 'string') {
    if (typeof value !== 'string' || schema.minLength !== undefined && value.length < schema.minLength || schema.maxLength !== undefined && value.length > schema.maxLength) return invalid()
    if (schema.pattern && !new RegExp(schema.pattern).test(value) || schema.format === 'date-time' && !Number.isFinite(Date.parse(value))) return invalid()
    return value
  }
  if (schema.type === 'array') {
    if (!Array.isArray(value) || schema.minItems !== undefined && value.length < schema.minItems || schema.maxItems !== undefined && value.length > schema.maxItems) return invalid()
    return value.map((item, index) => validateSchema(item, schema.items ?? {}, root, path + '[' + index + ']'))
  }
  if (schema.type === 'object' || schema.properties) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return invalid()
    const source = value as Record<string, unknown>, result: Record<string, unknown> = {}, properties = schema.properties ?? {}
    for (const name of schema.required ?? []) if (source[name] === undefined) return invalid()
    for (const [key, item] of Object.entries(source)) {
      if (key in properties) result[key] = validateSchema(item, properties[key], root, path + '.' + key)
      else if (schema.additionalProperties === false) return invalid()
      else result[key] = schema.additionalProperties && schema.additionalProperties !== true ? validateSchema(item, schema.additionalProperties, root, path + '.' + key) : item
    }
    for (const [key, rule] of Object.entries(properties) as [string, any][]) if (!(key in result) && 'default' in rule) result[key] = structuredClone(rule.default)
    return result
  }
  return value
}
