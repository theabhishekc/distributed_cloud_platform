import React from 'react';
import { NavLink } from 'react-router-dom';

const navItems = [
  { path: '/cluster', label: 'CLUSTER STATE' },
  { path: '/tasks', label: 'TASK QUEUE' },
  { path: '/storage', label: 'DATA STORAGE' },
  { path: '/functions', label: 'FUNCTIONS' },
  { path: '/logs', label: 'SYSTEM LOGS' },
];

const Sidebar = () => {
  return (
    <div className="w-[220px] fixed top-0 left-0 h-screen bg-terminal-surface border-r border-terminal-border flex flex-col z-10 pt-16">
      <div className="flex-1 px-4 flex flex-col gap-2 mt-4">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 text-sm transition-colors border-l-2 ${
                isActive
                  ? 'text-terminal-cyan border-terminal-cyan bg-terminal-cyan/10'
                  : 'text-terminal-dim border-transparent hover:text-gray-300 hover:border-gray-600'
              }`
            }
          >
            {item.label}
          </NavLink>
        ))}
      </div>
      
      <div className="p-4 border-t border-terminal-border text-xs text-terminal-dim">
        <div className="flex items-center gap-2 mb-2">
          <div className="w-2 h-2 rounded-full bg-terminal-green animate-pulse" style={{ animation: 'pulse-green 2s infinite' }} />
          <span>MASTER ONLINE</span>
        </div>
        <div>IP: 192.168.1.10</div>
        <div>PORT: 8000</div>
      </div>
    </div>
  );
};

export default Sidebar;
