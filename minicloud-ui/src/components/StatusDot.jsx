import React from 'react';

const StatusDot = ({ status }) => {
  let bgClass = 'bg-[#22c55e]'; // healthy / active / online
  let animStyle = { animation: 'pulse-green 2s infinite' };

  if (status === 'degraded' || status === 'warning') {
    bgClass = 'bg-[#f59e0b]';
  } else if (status === 'dead' || status === 'offline' || status === 'error' || status === 'failed') {
    bgClass = 'bg-[#ef4444]';
    animStyle = {}; // no animation for dead
  }

  return (
    <div
      className={`w-2 h-2 rounded-full ${bgClass} inline-block shrink-0`}
      style={animStyle}
    />
  );
};

export default StatusDot;
