import React from 'react';

const FunctionList = ({ functions, selectedId, onSelect, onNew }) => {
  return (
    <div className="w-[40%] flex flex-col border-r border-terminal-border h-full overflow-hidden">
      <div className="p-4 border-b border-terminal-border flex justify-between items-center bg-terminal-surface">
        <h3 className="text-terminal-cyan font-bold tracking-widest text-sm">LAMBDA FUNCTIONS</h3>
        <button 
          onClick={onNew}
          className="bg-terminal-cyan/10 border border-terminal-cyan text-terminal-cyan px-3 py-1 hover:bg-terminal-cyan hover:text-black transition-colors text-xs cursor-pointer font-bold"
        >
          + NEW
        </button>
      </div>
      
      <div className="flex-1 overflow-y-auto">
        {(!functions || functions.length === 0) ? (
          <div className="p-6 text-terminal-dim font-mono text-sm text-center">
            NO FUNCTIONS REGISTERED <span className="animate-blink">_</span>
          </div>
        ) : (
          <div className="divide-y divide-terminal-border">
            {functions.map(fn => (
              <div 
                key={fn.function_id}
                onClick={() => onSelect(fn)}
                className={`p-4 cursor-pointer transition-colors border-l-2 ${
                  selectedId === fn.function_id 
                    ? 'border-terminal-cyan bg-terminal-cyan/5' 
                    : 'border-transparent hover:bg-terminal-border/30'
                }`}
              >
                <div className="flex justify-between items-start mb-1">
                  <div className="text-gray-200 font-bold truncate max-w-[200px]" title={fn.name}>{fn.name}</div>
                  <div className="text-[10px] text-terminal-cyan border border-terminal-cyan/30 px-1">{fn.runtime || 'python3.10'}</div>
                </div>
                <div className="flex justify-between text-[10px] text-terminal-dim">
                  <div>ID: {fn.function_id?.substring(0, 8)}</div>
                  <div>{fn.created_at ? new Date(fn.created_at).toLocaleDateString() : ''}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default FunctionList;
