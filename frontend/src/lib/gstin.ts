// Client-side GSTIN shape check for instant feedback. The server does the full checksum.
const GSTIN_PATTERN = /^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/

export function isGstinShapeValid(value: string): boolean {
  return GSTIN_PATTERN.test(value.replace(/\s/g, '').toUpperCase())
}
