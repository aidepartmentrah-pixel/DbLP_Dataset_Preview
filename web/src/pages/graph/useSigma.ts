import type Graph from "graphology";
import { useEffect, useRef } from "react";
import { Sigma } from "sigma";

export function useSigma(graph: Graph | null, onNodeClick?: (nodeId: string) => void) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const onClickRef = useRef(onNodeClick);
  onClickRef.current = onNodeClick;

  useEffect(() => {
    if (!containerRef.current || !graph) return;
    const sigma = new Sigma(graph, containerRef.current, {
      renderLabels: true,
      labelRenderedSizeThreshold: 8,
    });
    sigmaRef.current = sigma;
    sigma.on("clickNode", ({ node }) => onClickRef.current?.(node));

    return () => {
      sigma.kill();
      sigmaRef.current = null;
    };
  }, [graph]);

  useEffect(() => {
    sigmaRef.current?.refresh();
  });

  return containerRef;
}
