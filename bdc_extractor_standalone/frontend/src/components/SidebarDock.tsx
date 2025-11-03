type Props = {
  onSelect: () => void;
};

export function SidebarDock({ onSelect }: Props) {
  return (
    <aside className="h-full w-64 p-3 space-y-2">
      <div className="window">
        <div className="titlebar"><span className="text-sm">BDCs</span></div>
        <button className="w-full text-left px-3 py-2 hover:bg-panel/70 border-t border-silver/10" onClick={onSelect}>
          <div className="text-silver">OFS Capital</div>
          <div className="text-xs text-silver/60">Schedule 2025 Q3</div>
        </button>
      </div>
    </aside>
  );
}






