export const PINE_ENGINE_VERSION: string
export const unsupported: string[][]
export function codeOnly(source: string): string
export function checkPine(source: string): void
export function pineError(value: unknown): Error & {line?:number;column?:number}
