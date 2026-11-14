import { moneyStackLevels } from "@/lib/money.mjs";

/** Decorative relative scale; ChartFigure supplies the accessible data table. */
export function MoneyStack({ amount, maximum }: { amount: string | null; maximum: string | null }) {
  const levels = moneyStackLevels(amount, maximum);
  return (
    <svg
      viewBox="0 0 56 88"
      className="h-20 w-14 shrink-0"
      shapeRendering="crispEdges"
      aria-hidden="true"
    >
      {Array.from({ length: levels }, (_, index) => {
        const y = 78 - index * 8;
        return (
          <g key={index}>
            <polygon points={`5,${y} 12,${y - 4} 50,${y - 4} 43,${y}`} fill="#a7e6bd" />
            <rect x="5" y={y} width="38" height="7" fill="#26814c" />
            <polygon points={`43,${y} 50,${y - 4} 50,${y + 3} 43,${y + 7}`} fill="#175a36" />
            <rect x="11" y={y + 2} width="26" height="2" fill="#73cc90" />
          </g>
        );
      })}
    </svg>
  );
}
