import React from 'react';

const ScanLine = ({ text = 'LOADING...' }) => {
  return (
    <div className="w-full h-12 border border-[#1a1a2e] bg-[#0d0d1a] relative overflow-hidden flex items-center justify-center my-4">
      <div 
        className="absolute top-0 left-0 h-full w-[40%] opacity-15 pointer-events-none"
        style={{
          background: 'linear-gradient(90deg, transparent, #00d4ff 20%, transparent)',
          animation: 'scan 1.2s linear infinite'
        }}
      />
      <span className="text-[#00d4ff] text-xs tracking-widest font-mono animate-pulse">
        {text}
      </span>
    </div>
  );
};

export default ScanLine;
