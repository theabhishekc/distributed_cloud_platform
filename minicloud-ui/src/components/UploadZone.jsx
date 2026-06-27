import React, { useState, useRef } from 'react';
import { uploadFile } from '../api/storage';

const UploadZone = ({ onUploadSuccess }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [progress, setProgress] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setIsDragging(true);
    } else if (e.type === 'dragleave') {
      setIsDragging(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
  };

  const handleFileUpload = async (file) => {
    setProgress(0);
    setError(null);
    setResult(null);

    try {
      const data = await uploadFile(file, (percent) => setProgress(percent));
      setResult(data);
      if (onUploadSuccess) onUploadSuccess(data);
    } catch (err) {
      setError(err.message || 'Upload failed');
    } finally {
      // Keep progress visible to indicate completion
    }
  };

  return (
    <div className="w-full mb-8">
      <div 
        className={`w-full p-8 border border-dashed flex flex-col items-center justify-center cursor-pointer transition-colors relative
          ${isDragging ? 'border-terminal-cyan bg-terminal-cyan/10' : 'border-[#00d4ff66] bg-terminal-surface'}
        `}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
      >
        <input 
          type="file" 
          ref={fileInputRef} 
          onChange={handleChange} 
          className="hidden" 
        />
        
        {progress === null && !result && !error && (
          <div className="text-terminal-dim font-mono tracking-widest pointer-events-none">
            DROP FILE OR CLICK TO UPLOAD
          </div>
        )}

        {progress !== null && !result && !error && (
          <div className="w-full max-w-md pointer-events-none">
            <div className="text-terminal-cyan text-xs mb-2">UPLOADING... {progress}%</div>
            <div className="w-full h-1 bg-terminal-border">
              <div className="h-full bg-terminal-cyan transition-all duration-300" style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}

        {result && (
          <div className="text-terminal-green font-mono pointer-events-none">
            ✓ FILE_ID: {result.file_id?.substring(0, 8)}  CHUNKS: {result.chunk_count || 1}  REPLICAS: {result.replication_factor || 2}
          </div>
        )}

        {error && (
          <div className="text-terminal-red font-mono pointer-events-none">
            ERR: {error}
          </div>
        )}
      </div>
    </div>
  );
};

export default UploadZone;
