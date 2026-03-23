import { type ReactNode, useState } from "react";

interface Tab {
  id: string;
  label: string;
  content: ReactNode;
}

interface BottomTabsProps {
  tabs: Tab[];
}

export default function BottomTabs({ tabs }: BottomTabsProps) {
  const [activeId, setActiveId] = useState(tabs[0]?.id ?? "");

  const activeTab = tabs.find((t) => t.id === activeId);

  return (
    <div className="flex flex-col bg-panel-surface border-t border-panel-border h-full">
      {/* Tab bar */}
      <div className="flex items-center border-b border-panel-border px-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveId(tab.id)}
            className={`px-3 py-1.5 text-sm font-medium border-b-2 transition-all duration-200 ${
              activeId === tab.id
                ? "border-accent-blue text-accent-blue"
                : "border-transparent text-text-secondary hover:text-text-primary"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto p-2 animate-fade-in" key={activeId}>
        {activeTab?.content}
      </div>
    </div>
  );
}
