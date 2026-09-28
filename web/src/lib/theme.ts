import * as echarts from "echarts";

// §9.3: "Register one ECharts theme (dblpTheme) built from the tokens, so
// every chart matches." Reads the live CSS custom properties so light/dark
// mode (§9.1) are picked up without a second copy of the palette.
function token(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

let registered = false;

export function registerDblpTheme(): void {
  if (registered) return;
  registered = true;

  const border = token("--border");
  const text = token("--text");
  const muted = token("--muted");
  const accent = token("--accent");

  echarts.registerTheme("dblpTheme", {
    color: [
      token("--cat-1"), token("--cat-2"), token("--cat-3"),
      token("--cat-4"), token("--cat-5"), token("--cat-6"),
    ],
    backgroundColor: "transparent",
    textStyle: { color: text, fontFamily: "Inter, system-ui, sans-serif" },
    title: { textStyle: { color: text, fontWeight: 600, fontSize: 14 } },
    grid: { borderColor: border },
    categoryAxis: {
      axisLine: { lineStyle: { color: border } },
      axisTick: { lineStyle: { color: border } },
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: border } },
    },
    valueAxis: {
      axisLine: { lineStyle: { color: border } },
      axisTick: { lineStyle: { color: border } },
      axisLabel: { color: muted },
      splitLine: { lineStyle: { color: border } },
    },
    line: { lineStyle: { width: 2 } },
    tooltip: {
      backgroundColor: token("--surface"),
      borderColor: border,
      textStyle: { color: text },
    },
  });
}

export const accentColor = () => token("--accent");
export const mutedColor = () => token("--muted");
export const journalColor = () => token("--cat-1");
export const conferenceColor = () => token("--cat-2");
export const sequentialRamp = (): [string, string] => ["#EEF2FF", "#3730A3"];
