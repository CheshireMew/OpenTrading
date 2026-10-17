export function createMessageTranslator(
  catalogs: Record<string, string>[],
  translate: (key: string, params: Record<string, string>) => string,
): (value: unknown) => string
