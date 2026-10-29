import type { Register, SessionContextUsage, SessionCost, SessionRateLimit } from 'claude-code'

const LIMIT_LABELS: Record<string, string> = { five_hour: '5h', seven_day: '7d', spend_limit: 'spend' }
const GAUGE_CELLS = 10
const WARN_PERCENT = 80

const formatTokens = (n: number) =>
  n >= 1_000_000 ? `${+(n / 1_000_000).toFixed(1)}M` : n >= 1000 ? `${Math.round(n / 1000)}k` : `${n}`

const formatGauge = (percent: number) => {
  const filled = Math.min(GAUGE_CELLS, Math.max(0, Math.round(percent / (100 / GAUGE_CELLS))))
  return '▰'.repeat(filled) + '▱'.repeat(GAUGE_CELLS - filled)
}

const formatDuration = (ms: number) => {
  const minutes = Math.max(0, Math.round(ms / 60_000))
  const days = Math.floor(minutes / 1440)
  const hours = Math.floor((minutes % 1440) / 60)
  if (days > 0) return `${days}d${hours}h`
  return hours > 0 ? `${hours}h${minutes % 60}m` : `${minutes}m`
}

const formatCost = (usd: number) => (usd < 10 ? `$${usd.toFixed(2)}` : `$${usd.toFixed(1)}`)

export const formatLine = (
  context: SessionContextUsage,
  rateLimits: SessionRateLimit[],
  cost: SessionCost | undefined,
  now: number,
) => {
  const percent = context.percent ?? 0
  const used = context.tokens === undefined ? '–' : formatTokens(context.tokens)
  const warn = percent >= WARN_PERCENT ? '⚠ ' : ''
  const ctx = `${warn}${formatGauge(percent)} ${used}/${formatTokens(context.window)} ${percent}%`

  const limits = rateLimits.map(l => {
    const label = LIMIT_LABELS[l.kind] ?? l.kind
    const resetsAt = l.resetsAt === undefined ? NaN : Date.parse(l.resetsAt)
    const reset = Number.isNaN(resetsAt) ? '' : ` ↻${formatDuration(resetsAt - now)}`
    return `${label} ${l.percentUsed}%${reset}`
  })

  const spent = cost === undefined ? [] : [`${formatCost(cost.usd)} session`]

  return [ctx, ...limits, ...spent].join('  │  ')
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    const { context, rateLimits, cost } = await $.session.usage()
    $.ui.status(formatLine(context, rateLimits, cost, await $.clock.now()))
    return result
  })

  on('session.measure', async ($, e, next) => {
    $.ui.status(formatLine(e.context, e.rateLimits, e.cost, await $.clock.now()))
    return next(e)
  })
}
