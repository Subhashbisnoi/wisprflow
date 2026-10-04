import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatINR, formatINRCompact, formatMonth } from '@/lib/format'
import type { DashboardSummary } from '@/lib/types'
import styles from './Dashboard.module.css'

type Row = DashboardSummary['monthly_spend'][number]

/** Chart colours come from tokens.css so the token file stays the single source (D-081). */
function useTokens() {
  return useMemo(() => {
    const css = getComputedStyle(document.documentElement)
    const read = (name: string) => css.getPropertyValue(name).trim()
    return {
      approved: read('--chart-approved'),
      pending: read('--chart-pending'),
      grid: read('--chart-grid'),
      axis: read('--chart-axis'),
      surface: read('--color-surface'),
      text: read('--color-text'),
      border: read('--color-border'),
    }
  }, [])
}

export function SpendChart({ data }: { data: Row[] }) {
  const t = useTokens()
  const rows = data.map((r) => ({
    month: formatMonth(r.month),
    approved: Number(r.approved),
    pending: Number(r.pending),
  }))

  return (
    <figure className={styles.chartFigure}>
      <div className={styles.chart} aria-hidden="true">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={rows}
            margin={{ top: 8, right: 8, left: 8, bottom: 0 }}
            barCategoryGap="32%"
          >
            <CartesianGrid vertical={false} stroke={t.grid} />
            <XAxis
              dataKey="month"
              tickLine={false}
              axisLine={{ stroke: t.border }}
              tick={{ fill: t.axis, fontSize: 12 }}
            />
            <YAxis
              tickFormatter={(v: number) => formatINRCompact(v)}
              tickLine={false}
              axisLine={false}
              tick={{ fill: t.axis, fontSize: 12 }}
              width={64}
            />
            <Tooltip
              cursor={{ fill: t.grid, fillOpacity: 0.5 }}
              formatter={(value, name) => [
                formatINR(Number(value)),
                name === 'approved' ? 'Approved' : 'Pending review',
              ]}
              contentStyle={{
                borderRadius: 8,
                border: `1px solid ${t.border}`,
                boxShadow: '0 4px 12px rgba(15, 23, 42, 0.07)',
                fontSize: 13,
                color: t.text,
              }}
            />
            <Legend
              verticalAlign="top"
              align="right"
              iconType="square"
              iconSize={10}
              height={28}
              formatter={(value: string) => (
                <span style={{ color: t.text, fontSize: 12 }}>
                  {value === 'approved' ? 'Approved' : 'Pending review'}
                </span>
              )}
            />
            {/* 2px surface stroke separates stacked segments; rounded data-end on top only. */}
            <Bar
              dataKey="approved"
              stackId="spend"
              fill={t.approved}
              stroke={t.surface}
              strokeWidth={2}
              maxBarSize={44}
              animationDuration={400}
            />
            <Bar
              dataKey="pending"
              stackId="spend"
              fill={t.pending}
              stroke={t.surface}
              strokeWidth={2}
              radius={[4, 4, 0, 0]}
              maxBarSize={44}
              animationDuration={400}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {/* Table view for screen readers and anyone who prefers exact numbers. */}
      <table className="visually-hidden">
        <caption>Monthly spend: approved and pending review</caption>
        <thead>
          <tr>
            <th scope="col">Month</th>
            <th scope="col">Approved</th>
            <th scope="col">Pending review</th>
          </tr>
        </thead>
        <tbody>
          {data.map((r) => (
            <tr key={r.month}>
              <th scope="row">{formatMonth(r.month)}</th>
              <td>{formatINR(r.approved)}</td>
              <td>{formatINR(r.pending)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
