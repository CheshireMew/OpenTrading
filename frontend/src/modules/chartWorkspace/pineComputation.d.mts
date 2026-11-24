export function runPineComputation(input: any, options: {
  write?: (name: string, value: any) => void
  hash: (value: unknown) => string | Promise<string>
  runtimeVersion?: string
  reportOnly?: boolean
}): Promise<any>
