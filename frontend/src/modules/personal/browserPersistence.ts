export function browserStorageError(cause: unknown): Error {
  if (cause instanceof Error && cause.name !== 'QuotaExceededError') return cause
  return new Error((cause as { name?: string } | null)?.name === 'QuotaExceededError'
    ? 'Browser storage is full; export your data first' : 'Browser storage is unavailable')
}

// Backup identity is structural: JSON property order is not a user edit.
export function sameStoredValue(left: any, right: any): boolean {
  if (Object.is(left, right)) return true
  if (!left || !right || typeof left !== 'object' || typeof right !== 'object') return false
  if (Array.isArray(left) || Array.isArray(right)) {
    return Array.isArray(left) && Array.isArray(right) && left.length === right.length
      && left.every((value, index) => sameStoredValue(value, right[index]))
  }
  const keys = Object.keys(left)
  return keys.length === Object.keys(right).length
    && keys.every(key => Object.prototype.hasOwnProperty.call(right, key) && sameStoredValue(left[key], right[key]))
}
