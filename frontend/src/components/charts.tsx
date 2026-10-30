import { type ReactNode, useEffect, useId, useRef, useState } from "react";

export type Point = { label: string; value: number | null; detail?: string };

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
const PAD = { top: 22, right: 8, bottom: 28, left: 52 };

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

type ChartProps = {
  points: Point[]; format: (v: number) => string; title: string;
  changeFormat?: (now: number, before: number) => string; tickFormat?: (v: number) => string;
};

/** Tooltip shared by both charts: exact value, period and the change from the previous period. */
function Tooltip({ x, y, width, point, previous, format, changeFormat }: {
  x: number; y: number; width: number; point: Point; previous?: Point; format: (v: number) => string;
  changeFormat?: (now: number, before: number) => string;
}) {
  const left = Math.min(Math.max(x - 80, 0), width - 160);
  return (
    <div role="status" className="pointer-events-none absolute z-10 w-40 rounded-[6px] bg-raised px-3 py-2 shadow-[var(--shadow)]"
      style={{ left, top: Math.max(y - 64, 0) }}>
      <p className="num text-small text-muted">{point.label}</p>
      <p className="num text-ink">{point.value === null ? "Not reported" : format(point.value)}</p>
      {point.value !== null && previous?.value != null && changeFormat && (
        <p className="num text-small text-muted">{changeFormat(point.value, previous.value)} vs {previous.label}</p>
      )}
      {point.detail && <p className="text-small text-muted">{point.detail}</p>}
    </div>
  );
}

function Frame({ W, ticks, format, y, children, title, desc }: {
  W: number; ticks: number[]; format: (v: number) => string; y: (v: number) => number; children: ReactNode; title: string; desc: string;
}) {
  const id = useId();
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} className="block" role="group" aria-labelledby={`${id}-t ${id}-d`}>
      <title id={`${id}-t`}>{title}</title>
      <desc id={`${id}-d`}>{desc}</desc>
      {ticks.map((t) => (
        <g key={t} aria-hidden="true">
          <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} stroke="var(--grid)" strokeWidth={t === 0 ? 1.5 : 1} />
          <text x={PAD.left - 8} y={y(t)} dy="0.32em" textAnchor="end" fontSize="11" fill="var(--muted)" className="num">{format(t)}</text>
        </g>
      ))}
      {children}
    </svg>
  );
}

function scale(points: Point[]) {
  const values = points.map((p) => p.value).filter((v): v is number => v !== null);
  const ticks = niceTicks(Math.min(...values), Math.max(...values));
  const lo = ticks[0]!;
  const hi = ticks[ticks.length - 1]!;
  return { values, ticks, y: (v: number) => PAD.top + (H - PAD.top - PAD.bottom) * (1 - (v - lo) / (hi - lo)) };
}

const describe = (points: Point[], format: (v: number) => string) =>
  points.map((p) => `${p.label}: ${p.value === null ? "not reported" : format(p.value)}`).join("; ");

/** Columns per period; the latest period carries the accent. Hover or focus a column for its exact value. */
export function BarChart(props: ChartProps) {
  const [ref, W] = useWidth();
  const [active, setActive] = useState<number | null>(null);
  const { points, format, title } = props;
  if (!points.some((p) => p.value !== null)) return <p className="text-muted">No values reported.</p>;
  const { ticks, y } = scale(points);
  const band = (W - PAD.left - PAD.right) / points.length;
  const barWidth = Math.min(56, band * 0.56);
  const x = (i: number) => PAD.left + band * i + (band - barWidth) / 2;

  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setActive(null)}>
      <Frame W={W} ticks={ticks} format={props.tickFormat ?? format} y={y} title={title} desc={describe(points, format)}>
        {points.map((p, i) => {
          const latest = i === points.length - 1;
          const top = p.value === null ? y(0) : Math.min(y(p.value), y(0));
          return (
            <g key={p.label} tabIndex={0} role="img" aria-label={`${p.label}: ${p.value === null ? "not reported" : format(p.value)}`}
              onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}
              className="cursor-default focus:outline-none">
              <rect x={PAD.left + band * i} y={PAD.top} width={band} height={H - PAD.top - PAD.bottom} fill="transparent" />
              {p.value !== null && (
                <rect x={x(i)} width={barWidth} y={top} height={Math.abs(y(0) - y(p.value))}
                  fill={latest ? "var(--accent)" : "var(--control)"} opacity={active === null || active === i ? 1 : 0.55} />
              )}
              {p.value !== null && (
                <text x={x(i) + barWidth / 2} y={y(Math.max(p.value, 0)) - 6} textAnchor="middle" fontSize="11"
                  fill={latest ? "var(--text)" : "var(--muted)"} className="num" aria-hidden="true">{format(p.value)}</text>
              )}
              <text x={x(i) + barWidth / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--muted)" className="num" aria-hidden="true">{p.label}</text>
            </g>
          );
        })}
      </Frame>
      {active !== null && points[active] && (
        <Tooltip x={x(active) + barWidth / 2} y={points[active]!.value === null ? y(0) : y(Math.max(points[active]!.value!, 0))}
          width={W} point={points[active]!} previous={points[active - 1]} format={format} changeFormat={props.changeFormat} />
      )}
    </div>
  );
}

/** One straight-segment line; every period is focusable and the latest carries a label. */
export function LineChart(props: ChartProps) {
  const [ref, W] = useWidth();
  const [active, setActive] = useState<number | null>(null);
  const { points, format, title } = props;
  if (points.filter((p) => p.value !== null).length < 2) return <p className="text-muted">Not enough reported years to draw a trend.</p>;
  const { ticks, y } = scale(points);
  const step = (W - PAD.left - PAD.right) / points.length;
  const x = (i: number) => PAD.left + step * i + step / 2;
  const coords = points.map((p, i) => (p.value === null ? null : ([x(i), y(p.value)] as const)));
  const path = coords.reduce((d, c, i) => (c ? `${d}${d && coords[i - 1] ? "L" : "M"}${c[0]},${c[1]}` : d), "");
  const lastIndex = points.length - 1;

  return (
    <div ref={ref} className="relative w-full" onMouseLeave={() => setActive(null)}>
      <Frame W={W} ticks={ticks} format={props.tickFormat ?? format} y={y} title={title} desc={describe(points, format)}>
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth={2} aria-hidden="true" />
        {points.map((p, i) => {
          const c = coords[i];
          return (
            <g key={p.label} tabIndex={0} role="img" aria-label={`${p.label}: ${p.value === null ? "not reported" : format(p.value)}`}
              onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)} className="focus:outline-none">
              <rect x={x(i) - step / 2} y={PAD.top} width={step} height={H - PAD.top - PAD.bottom} fill="transparent" />
              {c && (active === i || i === lastIndex) && <circle cx={c[0]} cy={c[1]} r={active === i ? 4.5 : 3.5} fill="var(--accent)" />}
              {c && i === lastIndex && active === null && (
                <text x={c[0]} y={c[1] - 10} textAnchor="middle" fontSize="11" fill="var(--text)" className="num" aria-hidden="true">{format(p.value!)}</text>
              )}
              <text x={x(i)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--muted)" className="num" aria-hidden="true">{p.label}</text>
            </g>
          );
        })}
      </Frame>
      {active !== null && points[active] && (
        <Tooltip x={x(active)} y={coords[active]?.[1] ?? y(0)} width={W} point={points[active]!} previous={points[active - 1]}
          format={format} changeFormat={props.changeFormat} />
      )}
    </div>
  );
}

/** 100% stacked bar with 2px seams: the verification ledger at a glance. */
export function LedgerBar({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((s, p) => s + p.value, 0);
  if (!total) return null;
  return (
    <div className="flex h-2.5 w-full gap-[2px]" role="img" aria-label={parts.map((p) => `${p.label} ${p.value}`).join(", ")}>
      {parts.filter((p) => p.value > 0).map((p) => (
        <span key={p.label} className="h-full first:rounded-l-[2px] last:rounded-r-[2px]" style={{ flexGrow: p.value, background: p.color }} />
      ))}
    </div>
  );
}
