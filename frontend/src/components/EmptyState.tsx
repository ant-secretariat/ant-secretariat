import { FileSearch } from "lucide-react";

export function EmptyState({ title, description }: { title: string; description?: string }) {
  return (
    <div className="empty-state">
      <FileSearch size={28} />
      <strong>{title}</strong>
      {description ? <span>{description}</span> : null}
    </div>
  );
}
