import React from 'react';

const CpuBar = ({ label = 'CPU', percentage = 0 }) => {
  const num = parseFloat(percentage) || 0;
  
  let fillBg = '#00d4ff'; // var(--cyan)
  if (num >= 70 && num <= 90) {
    fillBg = '#f59e0b'; // var(--amber)
  } else if (num > 90) {
    fillBg = '#ef4444'; // var(--red)
  }

  return (
    <div className="w-full my-1">
      <div className="text-[10px] text-[#4a4a6a] text-left font-mono mb-1">
        {label}&nbsp;&nbsp;{num.toFixed(1)}%
      </div>
      <div 
        className="w-full h-1 bg-transparent border border-[#1a1a2e] relative overflow-hidden rounded-none"
      >
        <div
          className="h-full absolute left-0 top-0"
          style={{
            width: `${Math.min(Math.max(num, 0), 100)}%`,
            backgroundColor: fillBg,
            transition: 'width 400ms ease',
          }}
        />
      </div>
    </div>
  );
};

export default CpuBar;
