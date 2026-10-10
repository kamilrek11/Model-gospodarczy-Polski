export function ChartSkeleton() {
  return (
    <div className="skeletons" aria-busy="true" aria-live="polite" data-testid="skeleton">
      <span className="sr-only">Obliczanie…</span>
      <div className="skeleton" />
      <div className="skeleton" />
    </div>
  );
}
