import React, { useState, useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';

const LiveClock = () => {
  const [time, setTime] = useState(new Date().toLocaleTimeString('en-US', { hour12: false }));

  useEffect(() => {
    const timer = setInterval(() => {
      setTime(new Date().toLocaleTimeString('en-US', { hour12: false }));
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  return <div className="text-terminal-cyan font-mono text-sm">{time} UTC</div>;
};

const Layout = () => {
  return (
    <div className="flex h-screen bg-terminal-bg text-gray-200 overflow-hidden">
      <div 
        className="fixed top-0 left-0 w-full h-16 border-b border-terminal-border flex items-center justify-between px-6 z-20"
        style={{ background: 'linear-gradient(to right, #0a0a0f, #0d0d1a)' }}
      >
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-bold tracking-widest">MINICLOUD CONTROL PLANE</h1>
          <span className="bg-terminal-cyan/20 text-terminal-cyan text-[10px] px-2 py-0.5 rounded-sm border border-terminal-cyan/30">
            v1.0.0
          </span>
        </div>
        <LiveClock />
      </div>

      <Sidebar />

      <main className="ml-[220px] mt-16 flex-1 h-[calc(100vh-64px)] overflow-y-auto p-6">
        <Outlet />
      </main>
    </div>
  );
};

export default Layout;
