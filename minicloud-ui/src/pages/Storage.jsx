import React, { useState, useEffect } from 'react';
import { listFiles } from '../api/storage';
import UploadZone from '../components/UploadZone';
import FileTable from '../components/FileTable';
import ScanLine from '../components/ScanLine';

const Storage = () => {
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchFiles = async () => {
    setLoading(true);
    try {
      const data = await listFiles();
      setFiles(Array.isArray(data) ? data : data.files || []);
      setError(null);
    } catch (err) {
      setError(err.message || 'Failed to fetch files');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchFiles();
  }, []);

  const handleUploadSuccess = () => {
    // Refresh files list after successful upload
    fetchFiles();
  };

  return (
    <div className="h-full flex flex-col">
      <h2 className="text-terminal-cyan font-bold tracking-widest mb-4">DISTRIBUTED DATA STORAGE</h2>
      
      <UploadZone onUploadSuccess={handleUploadSuccess} />

      <div className="flex-1">
        {loading ? (
          <ScanLine text="FETCHING FILES INDEX..." />
        ) : error ? (
          <div className="text-terminal-red p-4 border border-terminal-red/30 bg-terminal-red/10">ERR: {error}</div>
        ) : (
          <FileTable files={files} />
        )}
      </div>
    </div>
  );
};

export default Storage;
