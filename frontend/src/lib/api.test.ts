import { ApiError, buildQuery } from './api'

describe('buildQuery', () => {
  it('skips empty values and repeats arrays', () => {
    expect(
      buildQuery({ status: ['needs_review', 'failed'], search: '', page: 2, vendor: undefined }),
    ).toBe('?status=needs_review&status=failed&page=2')
  })
})

describe('ApiError', () => {
  it('maps validation details to field errors', () => {
    const err = new ApiError(422, 'validation_error', 'Some fields are invalid.', [
      { field: 'email', message: 'value is not a valid email address' },
      { field: 'company_gstin', message: 'Value error, GSTIN is not valid' },
    ])
    expect(err.fieldErrors()).toEqual({
      email: 'value is not a valid email address',
      company_gstin: 'GSTIN is not valid',
    })
  })
})
