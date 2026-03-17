import Sparkline from "./Sparkline";

interface ModelRow {
  model: string;
  config: string;
  accuracy: number;
  costPer1k: number;
  costPerCorrect: number;
  trend: number;
  ensemble: boolean;
}

interface CostTableProps {
  id: string;
  title: string;
  benchmark: string;
  description: string;
  data: ModelRow[];
}

export default function CostTable({ id, title, benchmark, description, data }: CostTableProps) {
  // Sort by cost per correct (ensemble first, then by cost ascending, free models last)
  const sorted = [...data].sort((a, b) => {
    if (a.ensemble) return -1;
    if (b.ensemble) return 1;
    if (a.costPerCorrect === 0) return 1;
    if (b.costPerCorrect === 0) return -1;
    return a.costPerCorrect - b.costPerCorrect;
  });

  return (
    <section id={id} style={{ marginBottom: 28 }}>
      <h2>{title}</h2>
      <p style={{ fontSize: 12, color: "#666", marginBottom: 4 }}>
        <strong>Benchmark:</strong> {benchmark}
      </p>
      <p style={{ fontSize: 11, color: "#888", marginBottom: 10, maxWidth: 640 }}>
        {description}
      </p>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Model</th>
            <th>Provider / Config</th>
            <th style={{ textAlign: "right" }}>Accuracy</th>
            <th style={{ textAlign: "right" }}>$/1k queries</th>
            <th style={{ textAlign: "right" }}>$/correct answer</th>
            <th style={{ textAlign: "right" }}>7d</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr
              key={row.model}
              style={row.ensemble ? { background: "#fff8e1" } : undefined}
            >
              <td style={{ color: "#999", fontSize: 11 }}>{i + 1}</td>
              <td style={row.ensemble ? { fontWeight: "bold", color: "#c8842a" } : undefined}>
                {row.model}
              </td>
              <td style={{ color: "#666" }}>{row.config}</td>
              <td style={{ textAlign: "right" }}>{row.accuracy.toFixed(1)}%</td>
              <td style={{ textAlign: "right" }}>
                {row.costPer1k === 0 ? (
                  <span style={{ color: "#999" }}>free*</span>
                ) : (
                  `$${row.costPer1k.toLocaleString()}`
                )}
              </td>
              <td style={{ textAlign: "right" }}>
                {row.costPerCorrect === 0 ? (
                  <span style={{ color: "#999" }}>free*</span>
                ) : (
                  `$${row.costPerCorrect.toFixed(2)}`
                )}
              </td>
              <td style={{ textAlign: "right", fontSize: 11 }}>
                {row.trend === 0 ? (
                  <span style={{ color: "#999" }}>—</span>
                ) : row.trend < 0 ? (
                  <span style={{ color: "#006600" }}>
                    <Sparkline
                      data={generateTrendData(row.costPerCorrect, row.trend)}
                      color="#006600"
                    />
                    {" "}↓{Math.abs(row.trend)}%
                  </span>
                ) : (
                  <span style={{ color: "#cc0000" }}>
                    <Sparkline
                      data={generateTrendData(row.costPerCorrect, row.trend)}
                      color="#cc0000"
                    />
                    {" "}↑{row.trend}%
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: 10, color: "#999", marginTop: 2 }}>
        * Local models run on your hardware. Actual cost depends on electricity and GPU amortization.
        Sorted by cost per correct answer (cheapest first).
      </p>
    </section>
  );
}

function generateTrendData(current: number, trendPct: number): number[] {
  if (current === 0) return [0, 0, 0, 0, 0, 0, 0];
  const start = current / (1 + trendPct / 100);
  const points: number[] = [];
  for (let i = 0; i < 7; i++) {
    points.push(start + (current - start) * (i / 6));
  }
  return points;
}
