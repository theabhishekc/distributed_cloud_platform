import React, { useState, useEffect } from 'react';
import { listFunctions } from '../api/functions';
import FunctionList from '../components/FunctionList';
import FunctionEditor from '../components/FunctionEditor';
import ScanLine from '../components/ScanLine';

const Functions = () => {
  const [functions, setFunctions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  
  const [selectedFn, setSelectedFn] = useState(null);

  const fetchFunctions = async () => {
    setLoading(true);
    try {
      const data = await listFunctions();
      setFunctions(Array.isArray(data) ? data : data.functions || []);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to fetch functions');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFunctions();
  }, []);

  const handleFunctionCreated = (newFn) => {
    setFunctions(prev => [...prev, newFn]);
    setSelectedFn(newFn);
  };

  return (
    <div className="h-full flex border border-terminal-border bg-terminal-surface shadow-2xl relative">
      {(loading && functions.length === 0) ? (
        <div className="absolute inset-0 flex items-center justify-center bg-terminal-bg/80 z-10 backdrop-blur-sm">
          <div className="w-1/2">
            <ScanLine text="FETCHING LAMBDAS..." />
          </div>
        </div>
      ) : null}

      {error && functions.length === 0 ? (
        <div className="w-full p-4 text-terminal-red">ERR: {error}</div>
      ) : (
        <>
          <FunctionList 
            functions={functions} 
            selectedId={selectedFn?.function_id} 
            onSelect={setSelectedFn} 
            onNew={() => setSelectedFn(null)}
          />
          <FunctionEditor 
            selectedFunction={selectedFn} 
            onFunctionCreated={handleFunctionCreated} 
            onCancelNew={() => setSelectedFn(functions[0] || null)}
          />
        </>
      )}
    </div>
  );
};

export default Functions;
