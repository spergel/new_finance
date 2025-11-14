import { ReactNode, useState } from 'react';
import { playClickSound } from '../utils/sounds';

type TabItem = {
  id: string;
  label: string;
  content: ReactNode;
};

type TabsProps = {
  tabs: TabItem[];
  initialId?: string;
  onChange?: (id: string) => void;
  className?: string;
};

export function Tabs({ tabs, initialId, onChange, className }: TabsProps) {
  const [activeId, setActiveId] = useState<string>(initialId ?? (tabs[0]?.id ?? ''));

  const activate = (id: string) => {
    playClickSound();
    setActiveId(id);
    onChange?.(id);
  };

  const active = tabs.find(t => t.id === activeId) ?? tabs[0];

  return (
    <div className={`flex flex-col h-full ${className ?? ''}`}>
      <div className="flex flex-wrap gap-1 px-2 flex-shrink-0">
        {tabs.map(t => {
          const isActive = t.id === active?.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => activate(t.id)}
              className={`relative px-3 py-1 text-xs font-medium border-0 border-b-2 ${
                isActive 
                  ? 'text-black bg-white border-b-white' 
                  : 'text-black bg-[#c0c0c0] border-b-[#c0c0c0] hover:bg-[#d4d0c8]'
              }`}
              style={{
                border: '2px outset #c0c0c0',
                borderTop: '2px solid #ffffff',
                borderLeft: '2px solid #ffffff',
                borderRight: '2px solid #808080',
                borderBottom: isActive ? '2px solid #ffffff' : '2px solid #808080',
                marginBottom: isActive ? '-2px' : '0',
                zIndex: isActive ? 10 : 1,
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      <div className="mt-0 flex-1 min-h-0 flex flex-col bg-white border-t-2 border-t-[#c0c0c0]">
        {active?.content}
      </div>
    </div>
  );
}


