import { useEffect, useState } from 'react';
import './index.css';
import './styles.css';
import { SidebarDock } from './components/SidebarDock';
import { TickerWindow } from './components/TickerWindow';
import { HoldingsTable } from './components/HoldingsTable';
import { Holding, loadOFSCsv } from './data/adapter';

function App() {
  const [data, setData] = useState<Holding[]>([]);

  useEffect(() => {
    loadOFSCsv('/data/OFS_Schedule_Continued_2025Q3.csv').then(setData);
  }, []);

  return (
    <div className="h-full grid grid-cols-[16rem_1fr] gap-4 p-4">
      <SidebarDock onSelect={() => {}} />
      <div className="grid grid-rows-[240px_1fr] gap-4">
        <TickerWindow />
        <HoldingsTable data={data} />
      </div>
    </div>
  );
}

export default App
