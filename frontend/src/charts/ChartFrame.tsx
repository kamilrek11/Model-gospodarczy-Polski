import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

/**
 * Mierzy szerokość kontenera i przekazuje ją wykresowi (zamiast ResponsiveContainer,
 * który w jsdom ma rozmiar 0 i zgłasza ostrzeżenia). Przy szerokości 0 nic nie rysuje.
 */
export function ChartFrame({ height, children, label }: { height: number; label: string; children: (width: number) => ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setWidth(Math.floor(el.clientWidth));
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div ref={ref} className="chart-frame" style={{ height }} role="img" aria-label={label}>
      {width > 0 ? children(width) : null}
    </div>
  );
}
