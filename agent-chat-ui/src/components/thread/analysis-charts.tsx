"use client";

import { z } from "zod";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  ScatterChart,
  Scatter,
  CartesianGrid,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";

const chartSchema = z.object({
  recommended: z.boolean(),
  chart_type: z.enum(["bar", "line", "pie", "scatter"]).nullable(),
  step_id: z.number().int(),
  dataset_id: z.string().nullable(),
  dimensions: z.array(z.string()),
  metrics: z.array(z.string()),
  description: z.string(),
  reason: z.string(),
  data: z.array(
    z.record(z.string(), z.union([z.string(), z.number().finite(), z.null()])),
  ),
  units: z.record(z.string(), z.string().nullable()),
});

export type AnalysisChart = z.infer<typeof chartSchema>;

const colors = ["#2563eb", "#0d9488", "#b45309", "#7c3aed"];

export function AnalysisCharts({ value }: { value: unknown }) {
  const parsed = z.array(chartSchema).safeParse(value);
  if (!parsed.success) return null;
  return parsed.data
    .filter(
      (chart) => chart.recommended && chart.chart_type && chart.data.length > 0,
    )
    .map((chart, index) => {
      const dimension = chart.dimensions[0];
      const metric = chart.metrics[0];
      const fields = [...chart.dimensions, ...chart.metrics];
      if (
        !metric ||
        (chart.chart_type !== "scatter" && !dimension) ||
        (chart.chart_type === "scatter" && chart.metrics.length !== 2)
      )
        return null;
      if (
        chart.data.some(
          (row) =>
            chart.metrics.some((key) => typeof row[key] !== "number") ||
            chart.dimensions.some((key) => row[key] == null),
        )
      )
        return null;
      const unit = chart.units[metric] ?? "单位未知";
      let plot;
      if (chart.chart_type === "scatter") {
        const other = chart.metrics[1];
        plot = (
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              type="number"
              dataKey={metric}
              name={metric}
              unit={unit}
            />
            <YAxis
              type="number"
              dataKey={other}
              name={other}
              unit={chart.units[other] ?? "单位未知"}
            />
            <Tooltip />
            <Scatter
              data={chart.data}
              fill={colors[0]}
              isAnimationActive={false}
            />
          </ScatterChart>
        );
      } else if (chart.chart_type === "pie") {
        plot = (
          <PieChart>
            <Tooltip />
            <Legend />
            <Pie
              data={chart.data}
              dataKey={metric}
              nameKey={dimension}
              fill={colors[0]}
              label
              isAnimationActive={false}
            />
          </PieChart>
        );
      } else if (chart.chart_type === "line") {
        plot = (
          <LineChart data={chart.data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={dimension} />
            <YAxis unit={unit} />
            <Tooltip />
            <Legend />
            {chart.metrics.map((key, i) => (
              <Line
                key={key}
                dataKey={key}
                stroke={colors[i % colors.length]}
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        );
      } else {
        plot = (
          <BarChart data={chart.data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey={dimension} />
            <YAxis unit={unit} />
            <Tooltip />
            <Legend />
            {chart.metrics.map((key, i) => (
              <Bar
                key={key}
                dataKey={key}
                fill={colors[i % colors.length]}
                isAnimationActive={false}
              />
            ))}
          </BarChart>
        );
      }
      return (
        <figure
          key={`${chart.dataset_id}:${index}`}
          className="my-3 rounded-lg border p-4"
          aria-label={`步骤 ${chart.step_id} 图表`}
        >
          <figcaption className="mb-3 text-sm">{chart.description}</figcaption>
          <div className="h-72 min-w-0">
            <ResponsiveContainer
              width="100%"
              height="100%"
            >
              {plot}
            </ResponsiveContainer>
          </div>
          <details className="mt-3 text-sm">
            <summary className="cursor-pointer">查看图表数据</summary>
            <div className="mt-2 overflow-auto">
              <table className="w-full text-left">
                <caption className="sr-only">
                  步骤 {chart.step_id} 图表数据
                </caption>
                <thead>
                  <tr>
                    {fields.map((field) => (
                      <th
                        key={field}
                        scope="col"
                        className="p-2"
                      >
                        {field}
                        {field in chart.units
                          ? `（${chart.units[field] ?? "单位未知"}）`
                          : ""}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {chart.data.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {fields.map((field) => (
                        <td
                          key={field}
                          className="p-2"
                        >
                          {String(row[field] ?? "—")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </figure>
      );
    });
}
