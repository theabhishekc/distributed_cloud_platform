import React, { useState, useEffect, useRef } from 'react';
import { createFunction, invokeFunction } from '../api/functions';
import StatusDot from './StatusDot';

const FunctionEditor = ({ selectedFunction, onFunctionCreated, onCancelNew }) => {
  const isNew = !selectedFunction;
  
  const [formData, setFormData] = useState({
    name: '',
    runtime: 'python3.10',
    code: 'def handler(event, context):\n    return {"message": "Hello"}'
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  // Invoke state
  const [payload, setPayload] = useState('{\n  "key": "value"\n}');
  const [timeoutSec, setTimeoutSec] = useState(30);
  const [invoking, setInvoking] = useState(false);
  const [invokeHistory, setInvokeHistory] = useState([]);
  
  const codeRef = useRef(null);
  const payloadRef = useRef(null);

  useEffect(() => {
    if (selectedFunction) {
      setFormData({
        name: selectedFunction.name,
        runtime: selectedFunction.runtime || 'python3.10',
        code: selectedFunction.code
      });
      setError(null);
    } else {
      setFormData({
        name: '',
        runtime: 'python3.10',
        code: 'def handler(event, context):\n    return {"message": "Hello from MiniCloud!"}'
      });
      setError(null);
      setInvokeHistory([]);
    }
  }, [selectedFunction]);

  const handleTab = (e, setter) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const target = e.target;
      const start = target.selectionStart;
      const end = target.selectionEnd;
      const val = target.value;
      setter(val.substring(0, start) + '    ' + val.substring(end));
      setTimeout(() => {
        target.selectionStart = target.selectionEnd = start + 4;
      }, 0);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const newFn = await createFunction({
        name: formData.name,
        runtime: formData.runtime,
        code: formData.code
      });
      if (onFunctionCreated) onFunctionCreated(newFn);
    } catch (err) {
      setError(err.message || 'Failed to create function');
    } finally {
      setSaving(false);
    }
  };

  const handleInvoke = async () => {
    if (!selectedFunction) return;
    setInvoking(true);
    try {
      let parsedPayload = {};
      try {
        parsedPayload = payload.trim() ? JSON.parse(payload) : {};
      } catch (e) {
        throw new Error('Invalid JSON payload');
      }

      const start = Date.now();
      const res = await invokeFunction(selectedFunction.function_id, parsedPayload, timeoutSec);
      
      const newHistoryItem = {
        id: Date.now(),
        timestamp: new Date().toISOString(),
        duration_ms: res.duration_ms || (Date.now() - start),
        status: res.error ? 'failed' : 'success',
        result: res
      };
      
      setInvokeHistory(prev => [newHistoryItem, ...prev].slice(0, 5));
    } catch (err) {
      const errItem = {
        id: Date.now(),
        timestamp: new Date().toISOString(),
        duration_ms: 0,
        status: 'failed',
        result: { error: err.message || 'Invocation failed' }
      };
      setInvokeHistory(prev => [errItem, ...prev].slice(0, 5));
    } finally {
      setInvoking(false);
    }
  };

  return (
    <div className="w-[60%] flex flex-col h-full bg-terminal-bg">
      {/* Code Editor Area */}
      <div className="h-1/2 flex flex-col border-b border-terminal-border p-4 bg-terminal-surface">
        <div className="flex justify-between items-center mb-4">
          <div className="flex gap-4 w-full mr-4">
            {isNew ? (
              <>
                <input 
                  placeholder="Function Name" 
                  value={formData.name}
                  onChange={e => setFormData({...formData, name: e.target.value})}
                  className="bg-terminal-bg border border-terminal-border p-2 text-sm text-gray-200 focus:border-terminal-cyan focus:outline-none flex-1 font-mono"
                />
                <input 
                  placeholder="Runtime" 
                  value={formData.runtime}
                  onChange={e => setFormData({...formData, runtime: e.target.value})}
                  className="bg-terminal-bg border border-terminal-border p-2 text-sm text-gray-200 focus:border-terminal-cyan focus:outline-none w-32 font-mono text-center"
                />
              </>
            ) : (
              <div className="flex items-center gap-4">
                <h3 className="text-terminal-cyan font-bold tracking-widest">{selectedFunction.name}</h3>
                <span className="text-xs text-terminal-dim border border-terminal-dim px-2 py-0.5">{selectedFunction.runtime}</span>
              </div>
            )}
          </div>
          
          {isNew && (
            <div className="flex gap-2">
              <button onClick={onCancelNew} className="text-terminal-dim hover:text-white px-3 py-1 cursor-pointer text-xs">CANCEL</button>
              <button 
                onClick={handleSave} 
                disabled={saving || !formData.name || !formData.code}
                className="bg-terminal-cyan text-black px-4 py-1 font-bold text-xs hover:bg-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {saving ? 'SAVING...' : 'SAVE'}
              </button>
            </div>
          )}
        </div>

        {error && <div className="text-terminal-red text-xs bg-terminal-red/10 p-2 border border-terminal-red mb-4">{error}</div>}

        <div className="flex-1 relative flex flex-col min-h-0">
          <div className="text-[10px] text-terminal-dim mb-1 flex justify-between">
            <span>SOURCE CODE</span>
            <span>Tab = 4 spaces</span>
          </div>
          <textarea
            ref={codeRef}
            value={formData.code}
            onChange={(e) => setFormData({...formData, code: e.target.value})}
            onKeyDown={(e) => handleTab(e, (v) => setFormData({...formData, code: v}))}
            disabled={!isNew}
            className="w-full flex-1 bg-[#050508] border border-terminal-border p-3 text-sm text-gray-300 font-mono focus:border-terminal-cyan focus:outline-none resize-none disabled:opacity-80"
            spellCheck="false"
          />
        </div>
      </div>

      {/* Invoke Area */}
      {!isNew && (
        <div className="h-1/2 flex flex-col p-4 bg-terminal-bg overflow-y-auto">
          <div className="flex gap-4 min-h-[120px] mb-4">
            <div className="flex-1 flex flex-col">
              <div className="text-[10px] text-terminal-dim mb-1">JSON PAYLOAD</div>
              <textarea
                ref={payloadRef}
                value={payload}
                onChange={(e) => setPayload(e.target.value)}
                onKeyDown={(e) => handleTab(e, setPayload)}
                className="w-full flex-1 bg-[#050508] border border-terminal-border p-3 text-xs text-gray-300 font-mono focus:border-terminal-cyan focus:outline-none resize-none"
                spellCheck="false"
              />
            </div>
            <div className="w-48 flex flex-col gap-4">
              <div className="space-y-1">
                <div className="text-[10px] text-terminal-dim">TIMEOUT (s)</div>
                <input 
                  type="number" 
                  value={timeoutSec} 
                  onChange={(e) => setTimeoutSec(Number(e.target.value))}
                  className="w-full bg-terminal-surface border border-terminal-border p-2 text-sm text-gray-200 focus:border-terminal-cyan focus:outline-none text-center font-mono"
                  min="1"
                  max="300"
                />
              </div>
              <button 
                onClick={handleInvoke}
                disabled={invoking}
                className="w-full flex-1 bg-terminal-cyan/10 border border-terminal-cyan text-terminal-cyan font-bold tracking-widest hover:bg-terminal-cyan hover:text-black transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {invoking ? 'INVOKING...' : 'INVOKE'}
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <div className="text-[10px] text-terminal-dim border-b border-terminal-border pb-1">INVOCATION HISTORY (LAST 5)</div>
            {invokeHistory.length === 0 ? (
              <div className="text-xs text-terminal-dim py-2">No recent invocations.</div>
            ) : (
              invokeHistory.map((item, idx) => {
                const res = item.result || {};
                return (
                  <div key={item.id} className="border border-terminal-border bg-terminal-surface p-3 text-xs font-mono">
                    <div className="flex justify-between items-center mb-2 border-b border-terminal-border/50 pb-2">
                      <div className="flex items-center gap-2">
                        <StatusDot status={item.status === 'success' ? 'healthy' : 'dead'} />
                        <span className="text-gray-300">{new Date(item.timestamp).toLocaleTimeString()}</span>
                      </div>
                      <div className="text-terminal-cyan">{item.duration_ms}ms</div>
                    </div>
                    <div className="whitespace-pre-wrap max-h-32 overflow-y-auto">
                      {res.error && (
                        <div className="text-terminal-red">{res.error}</div>
                      )}
                      {res.output !== undefined && (
                        <div className="text-terminal-green">{typeof res.output === 'object' ? JSON.stringify(res.output, null, 2) : res.output}</div>
                      )}
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}
      
      {isNew && (
        <div className="flex-1 flex items-center justify-center p-8 bg-terminal-bg text-terminal-dim text-sm font-mono text-center border-t border-terminal-border">
          Define your serverless function code above.<br />
          Click SAVE to deploy to the MiniCloud cluster.
        </div>
      )}
    </div>
  );
};

export default FunctionEditor;
