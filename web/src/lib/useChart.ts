import { useCallback, useEffect, useRef } from "react";
import * as echarts from "echarts";

import { registerDblpTheme } from "./theme";

type ChartEvents = Record<string, (params: echarts.ECElementEvent) => void>;

/** Creates (and tears down) one ECharts instance bound to a div, and
 * re-applies `option` whenever it changes. `onEvents` handlers are read via
 * a ref, so passing a fresh function each render never re-binds listeners.
 *
 * Real bug found via an actual browser screenshot (no chart canvas ever
 * rendered anything, despite the data clearly loading - visible from the
 * correct, data-derived subtitles): every chart's canvas `<div>` is only
 * mounted once its `ChartCard` reaches `status === "ready"` (see
 * ChartCard.tsx), which happens on a *later* re-render, not the first one.
 * A plain `useRef` + `useEffect(() => {...}, [])` only checks `ref.current`
 * once, at that first mount - when the div doesn't exist yet - so
 * `echarts.init()` never ran, and the later `setOption` calls silently had
 * no chart instance to apply to. A callback ref fixes this at the root:
 * React invokes it with the real DOM node exactly when it attaches
 * (including on a later re-render), and with `null` when it detaches. */
export function useChart(option: echarts.EChartsOption | null, onEvents?: ChartEvents) {
  const chartRef = useRef<echarts.ECharts | null>(null);
  const eventsRef = useRef<ChartEvents | undefined>(onEvents);
  eventsRef.current = onEvents;
  const optionRef = useRef<echarts.EChartsOption | null>(option);
  optionRef.current = option;

  const setRef = useCallback((node: HTMLDivElement | null) => {
    if (chartRef.current) {
      chartRef.current.dispose();
      chartRef.current = null;
    }
    if (!node) return;

    registerDblpTheme();
    const chart = echarts.init(node, "dblpTheme");
    chartRef.current = chart;
    for (const eventName of Object.keys(eventsRef.current ?? {})) {
      chart.on(eventName, (params) => eventsRef.current?.[eventName]?.(params as echarts.ECElementEvent));
    }
    if (optionRef.current) {
      chart.setOption(optionRef.current, true);
    }
  }, []);

  useEffect(() => {
    if (option && chartRef.current) {
      chartRef.current.setOption(option, true);
    }
  }, [option]);

  useEffect(() => {
    const onResize = () => chartRef.current?.resize();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return setRef;
}
