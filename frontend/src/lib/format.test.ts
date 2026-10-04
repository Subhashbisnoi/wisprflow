import { formatINR, formatINRCompact, formatPercent, pluralize } from './format'

describe('formatINR', () => {
  it('uses Indian lakh and crore grouping', () => {
    expect(formatINR('1234567.5')).toBe('₹12,34,567.50')
    expect(formatINR(123456789)).toBe('₹12,34,56,789.00')
  })
  it('falls back for missing values', () => {
    expect(formatINR(null)).toBe('-')
    expect(formatINR('abc', 'n/a')).toBe('n/a')
  })
  it('compacts for chart axes', () => {
    expect(formatINRCompact(1250000)).toContain('L')
  })
})

describe('misc formatters', () => {
  it('formats percent and plurals', () => {
    expect(formatPercent(0.6667)).toBe('67%')
    expect(formatPercent(null)).toBe('-')
    expect(pluralize(1, 'bill')).toBe('1 bill')
    expect(pluralize(3, 'bill')).toBe('3 bills')
  })
})
