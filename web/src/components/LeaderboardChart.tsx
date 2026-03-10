"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

// Placeholder HLE (Humanity's Last Exam) multiple choice benchmark scores.
// Replace with real data when available.
const data = [
  { model: "GPT-4o", score: 9.1, ensemble: false },
  { model: "Gemini 1.5 Pro", score: 10.3, ensemble: false },
  { model: "Claude 3.5 Sonnet", score: 8.7, ensemble: false },
  { model: "Llama 3 (Ollama)", score: 6.2, ensemble: false },
  { model: "😱 Ensemble", score: 16.8, ensemble: true },
];

const CustomTooltip = ({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { value: number }[];
  label?: string;
}) => {
  if (active && payload && payload.length) {
    return (
      <div className="bg-card border border-border rounded-lg px-4 py-3 text-sm">
        <p className="font-medium text-foreground mb-1">{label}</p>
        <p className="text-muted-foreground">
          HLE Score:{" "}
          <span className="text-foreground font-mono">
            {payload[0].value}%
          </span>
        </p>
      </div>
    );
  }
  return null;
};

export default function LeaderboardChart() {
  return (
    <div className="w-full">
      <div className="flex items-baseline justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold">HLE Benchmark</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Humanity&apos;s Last Exam — multiple choice accuracy
          </p>
        </div>
        <span className="text-xs text-muted-foreground font-mono border border-border rounded px-2 py-1">
          placeholder data
        </span>
      </div>

      <ResponsiveContainer width="100%" height={320}>
        <BarChart
          data={data}
          margin={{ top: 4, right: 4, left: -16, bottom: 0 }}
          barCategoryGap="28%"
        >
          <CartesianGrid
            vertical={false}
            stroke="oklch(1 0 0 / 8%)"
            strokeDasharray="3 3"
          />
          <XAxis
            dataKey="model"
            tick={{ fill: "oklch(0.708 0 0)", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "oklch(0.708 0 0)", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `${v}%`}
            domain={[0, 20]}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: "oklch(1 0 0 / 4%)" }} />
          <Bar dataKey="score" radius={[2, 2, 0, 0]}>
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={
                  entry.ensemble
                    ? "#f8c073"
                    : "#2e2a3a"
                }
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <p className="text-xs text-muted-foreground mt-4 text-center">
        The ensemble consistently outperforms any single model alone.
      </p>
    </div>
  );
}
