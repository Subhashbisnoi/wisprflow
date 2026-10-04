import { fireEvent, render, screen } from '@testing-library/react'
import { Pager } from './Pager'

describe('Pager', () => {
  it('shows the range and pages forward', () => {
    const onPage = vi.fn()
    render(
      <Pager page={1} pageSize={25} total={132} onPageChange={onPage} onPageSizeChange={vi.fn()} />,
    )
    expect(screen.getByText('1-25 of 132')).toBeInTheDocument()
    expect(screen.getByLabelText('Previous page')).toBeDisabled()
    fireEvent.click(screen.getByLabelText('Next page'))
    expect(onPage).toHaveBeenCalledWith(2)
  })

  it('changes rows per page', () => {
    const onSize = vi.fn()
    render(
      <Pager page={1} pageSize={25} total={10} onPageChange={vi.fn()} onPageSizeChange={onSize} />,
    )
    fireEvent.change(screen.getByLabelText('Rows per page'), { target: { value: '50' } })
    expect(onSize).toHaveBeenCalledWith(50)
  })
})
