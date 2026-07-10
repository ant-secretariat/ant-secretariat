export function LoadingBlock({ label = "불러오는 중" }: { label?: string }) {
  return (
    <div className="loading-block">
      <span className="spinner" />
      <span>{label}</span>
    </div>
  );
}
