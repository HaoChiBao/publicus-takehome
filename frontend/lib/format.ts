export function formatCurrency(value?: number | null): string {
  if (value === null || value === undefined) return "—";
  if (Math.abs(value) >= 1_000_000)
    return `$${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `$${(value / 1_000).toFixed(0)}K`;
  return `$${value.toLocaleString()}`;
}

export function formatCurrencyFull(value?: number | null): string {
  if (value === null || value === undefined) return "—";
  return `$${Math.round(value).toLocaleString()}`;
}

export function amountRange(min?: number | null, max?: number | null): string {
  if (min == null && max == null) return "Amount varies";
  if (min != null && max != null && min !== max)
    return `${formatCurrency(min)} – ${formatCurrency(max)}`;
  return formatCurrency(max ?? min);
}
