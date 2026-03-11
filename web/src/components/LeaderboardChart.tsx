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
  LabelList,
} from "recharts";

// Placeholder HLE (Humanity's Last Exam) multiple choice benchmark scores.
// Replace with real data when available.
// Sorted high→low so the best performer renders at the top.
const data = [
  { model: "😱 Ensemble", score: 16.8, ensemble: true },
  { model: "Gemini 1.5 Pro", score: 10.3, ensemble: false },
  { model: "GPT-4o", score: 9.1, ensemble: false },
  { model: "Claude 3.5 Sonnet", score: 8.7, ensemble: false },
  { model: "Llama 3 (Ollama)", score: 6.2, ensemble: false },
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
      <div className="bg-card border border-border rounded-lg px-4 py-3 text-sm shadow-lg">
        <p className="font-medium text-foreground mb-1">{label}</p>
        <p className="text-muted-foreground">
          HLE accuracy:{" "}
          <span
            className="text-foreground font-medium"
            style={{ fontFamily: "var(--font-sometype-mono)" }}
          >
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
      {/* Header */}
      <div className="flex items-start justify-between mb-8 gap-4">
        <div>
          <h3
            className="text-base font-semibold text-foreground"
            style={{ fontFamily: "var(--font-rubik)" }}
          >
            HLE Benchmark
          </h3>
          <p className="text-xs text-muted-foreground mt-1">
            Humanity&apos;s Last Exam — multiple choice accuracy (%)
          </p>
        </div>
        <span
          className="text-xs text-muted-foreground border border-border rounded px-2 py-1 shrink-0"
          style={{ fontFamily: "var(--font-sometype-mono)" }}
        >
          placeholder data
        </span>
      </div>

      {/* Horizontal bar chart */}
      <ResponsiveContainer width="100%" height={240}>
        <BarChart
          data={data}
          layout="vertical"
          margin={{ top: 0, right: 48, left: 0, bottom: 0 }}
          barCategoryGap="30%"
        >
          <CartesianGrid
            horizontal={false}
            stroke="oklch(1 0 0 / 6%)"
            strokeDasharray="4 4"
          />
          <XAxis
            type="number"
            domain={[0, 20]}
            tick={{ fill: "oklch(0.6 0 0)", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `${v}%`}
          />
          <YAxis
            type="category"
            dataKey="model"
            tick={{ fill: "oklch(0.72 0 0)", fontSize: 12 }}
            axisLine={false}
            tickLine={false}
            width={148}
          />
          <Tooltip
            content={<CustomTooltip />}
            cursor={{ fill: "oklch(1 0 0 / 3%)" }}
          />
          <Bar dataKey="score" radius={[0, 3, 3, 0]}>
            <LabelList
              dataKey="score"
              position="right"
              formatter={(v) => `${v}%`}
              style={{
                fill: "oklch(0.72 0 0)",
                fontSize: 11,
                fontFamily: "var(--font-sometype-mono)",
              }}
            />
            {data.map((entry, index) => (
              <Cell
                key={`cell-${index}`}
                fill={entry.ensemble ? "#f8c073" : "oklch(0.32 0.04 280)"}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
