import { type ReactNode, useEffect, useId, useRef, useState } from "react";

export type Point = { label: string; value: number | null };

function niceStep(range: number, ticks: number) {
  const raw = range / ticks;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const normalised = raw / magnitude;
  const step = normalised <= 1 ? 1 : normalised <= 2 ? 2 : normalised <= 2.5 ? 2.5 : normalised <= 5 ? 5 : 10;
  return step * magnitude;
}

/** Round, even ticks with the top tick above the maximum; zero included. */
export function niceTicks(min: number, max: number, count = 4): number[] {
  const lo = Math.min(0, min);
  const hi = Math.max(0, max);
  const step = niceStep(hi - lo || Math.abs(hi) || 1, count);
  const start = Math.floor(lo / step) * step;
  const ticks: number[] = [];
  for (let v = start; v <= hi + step * 0.001 || ticks.length < 2; v += step) ticks.push(Number(v.toPrecision(12)));
  if (ticks[ticks.length - 1]! <= hi) ticks.push(Number((ticks[ticks.length - 1]! + step).toPrecision(12)));
  return ticks;
}

const H = 200;

function useWidth() {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(520);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => entry && setWidth(Math.max(240, Math.round(entry.contentRect.width))));
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}
const PAD = { top: 22, right: 8, bottom: 28, left: 52 };

function Frame({ W, ticks, format, y, children, title, desc }: {
  W: number; ticks: number[]; format: (v: number) => string; y: (v: number) => number; children: ReactNode; title: string; desc: string;
}) {
  const id = useId();
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="block" role="img" aria-labelledby={`${id}-t ${id}-d`}>
      <title id={`${id}-t`}>{title}</title>
      <desc id={`${id}-d`}>{desc}</desc>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth={t === 0 ? 1.5 : 1} />
          <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize="11" fill="var(--muted)" className="num">{format(t)}</text>
        </g>
      ))}
      {children}
    </svg>
  );
}

/** Columns per period; the latest period carries the accent, earlier ones are neutral. */
export function BarChart(props: { points: Point[]; format: (v: number) => string; title: string }) {
  const [ref, W] = useWidth();
  return <div ref={ref} className="w-full overflow-hidden"><BarChartSvg {...props} W={W} /></div>;
}

function BarChartSvg({ points, format, title, W }: { points: Point[]; format: (v: number) => string; title: string; W: number }) {
  const values = points.map((p) => p.value).filter((v): v is number => v !== null);
  if (!values.length) return <p className="text-muted">No values reported.</p>;
  const ticks = niceTicks(Math.min(...values), Math.max(...values));
  const lo = ticks[0]!;
  const hi = ticks[ticks.length - 1]!;
  const y = (v: number) => PAD.top + (H - PAD.top - PAD.bottom) * (1 - (v - lo) / (hi - lo));
  const band = (W - PAD.left - PAD.right) / points.length;
  const barWidth = Math.min(56, band * 0.56);
  const desc = points.map((p) => `${p.label}: ${p.value === null ? "not reported" : format(p.value)}`).join("; ");

  return (
    <Frame W={W} ticks={ticks} format={format} y={y} title={title} desc={desc}>
      {points.map((p, i) => {
        const x = PAD.left + band * i + (band - barWidth) / 2;
        const latest = i === points.length - 1;
        return (
          <g key={p.label}>
            {p.value !== null && (
              <>
                <rect x={x} width={barWidth} y={Math.min(y(p.value), y(0))} height={Math.abs(y(0) - y(p.value))}
                  fill={latest ? "var(--accent)" : "var(--control)"} />
                <text x={x + barWidth / 2} y={y(Math.max(p.value, 0)) - 6} textAnchor="middle" fontSize="11"
                  fill={latest ? "var(--text)" : "var(--muted)"} className="num">{format(p.value)}</text>
              </>
            )}
            <text x={x + barWidth / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--muted)" className="num">{p.label}</text>
          </g>
        );
      })}
    </Frame>
  );
}

/** One straight-segment line, no markers except the latest point. */
export function LineChart(props: { points: Point[]; format: (v: number) => string; title: string }) {
  const [ref, W] = useWidth();
  return <div ref={ref} className="w-full overflow-hidden"><LineChartSvg {...props} W={W} /></div>;
}

function LineChartSvg({ points, format, title, W }: { points: Point[]; format: (v: number) => string; title: string; W: number }) {
  const present = points.filter((p): p is { label: string; value: number } => p.value !== null);
  if (present.length < 2) return <p className="text-muted">Not enough reported years to draw a trend.</p>;
  const values = present.map((p) => p.value);
  const ticks = niceTicks(Math.min(...values), Math.max(...values));
  const lo = ticks[0]!;
  const hi = ticks[ticks.length - 1]!;
  const y = (v: number) => PAD.top + (H - PAD.top - PAD.bottom) * (1 - (v - lo) / (hi - lo));
  const step = (W - PAD.left - PAD.right) / points.length;
  const x = (i: number) => PAD.left + step * i + step / 2;
  const coords = points.map((p, i) => (p.value === null ? null : ([x(i), y(p.value)] as const)));
  const path = coords.reduce((d, c, i) => (c ? `${d}${d && coords[i - 1] ? "L" : "M"}${c[0]},${c[1]}` : d), "");
  const last = coords[coords.length - 1];
  const desc = points.map((p) => `${p.label}: ${p.value === null ? "not reported" : format(p.value)}`).join("; ");

  return (
    <Frame W={W} ticks={ticks} format={format} y={y} title={title} desc={desc}>
      <path d={path} fill="none" stroke="var(--accent)" strokeWidth={2} />
      {last && (
        <>
          <circle cx={last[0]} cy={last[1]} r={3.5} fill="var(--accent)" />
          <text x={last[0]} y={last[1] - 10} textAnchor="middle" fontSize="11" fill="var(--text)" className="num">
            {format(points[points.length - 1]!.value!)}
          </text>
        </>
      )}
      {points.map((p, i) => (
        <text key={p.label} x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--muted)" className="num">{p.label}</text>
      ))}
    </Frame>
  );
}

/** 100% stacked bar with 2px seams: the verification ledger at a glance. */
export function LedgerBar({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0);
  if (!total) return null;
  return (
    <div className="flex h-2.5 w-full gap-[2px]" role="img"
      aria-label={parts.map((p) => `${p.label} ${p.value}`).join(", ")}>
      {parts.filter((p) => p.value > 0).map((p) => (
        <span key={p.label} className="h-full first:rounded-l-[2px] last:rounded-r-[2px]" style={{ flexGrow: p.value, background: p.color }} />
      ))}
    </div>
  );
}
