// A loading-style bar for agent spend in dollars. Every bar uses the human's $ limit as its scale,
// so they are directly comparable. Blue → amber (60%) → red (85%).

export const fmtUsd = (n: number) =>
  n === 0 ? "$0.00" : n < 0.01 ? `$${n.toFixed(4)}` : n < 1 ? `$${n.toFixed(3)}` : `$${n.toFixed(2)}`;

export const fmtTokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(n >= 100_000 ? 0 : 1)}k` : String(n));

interface Props {
  usd: number;
  limitUsd: number;
  label?: string;
  size?: "lg" | "sm";
  live?: boolean;
  dark?: boolean;
}

export function SpendBar({ usd, limitUsd, label, size = "sm", live = false, dark = false }: Props) {
  const pct = limitUsd > 0 ? Math.min(100, (usd / limitUsd) * 100) : 0;
  const level = pct >= 85 ? "high" : pct >= 60 ? "mid" : "low";
  return (
    <div className={`spend spend-${size} ${dark ? "spend-dark" : ""}`}>
      {label && (
        <div className="spend-label">
          <span>{label}</span>
          <span className="spend-num">{fmtUsd(usd)} / {fmtUsd(limitUsd)}</span>
        </div>
      )}
      <div
        className="spend-track"
        role="progressbar"
        aria-label={label ?? "Spend"}
        aria-valuemin={0}
        aria-valuemax={limitUsd}
        aria-valuenow={usd}
        aria-valuetext={`${fmtUsd(usd)} of the ${fmtUsd(limitUsd)} limit (${pct.toFixed(1)}%)`}
      >
        {/* a sliver stays visible once anything is spent, even when it's a tiny share of the limit */}
        <div className={`spend-fill spend-${level} ${live ? "spend-live" : ""}`} style={{ width: `${Math.max(pct, usd > 0 ? 1.5 : 0)}%` }} />
      </div>
    </div>
  );
}
