import React from 'react';
import { downloadFile } from '../api/storage';

const formatBytes = (bytes, decimals = 2) => {
  if (!+bytes) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
};

const FileTable = ({ files }) => {
  if (!files || files.length === 0) {
    return (
      <div className="w-full text-center py-8 text-terminal-dim font-mono border border-terminal-border bg-terminal-surface">
        NO FILES FOUND <span className="animate-blink">_</span>
      </div>
    );
  }

  return (
    <div className="w-full overflow-x-auto border border-terminal-border bg-terminal-surface">
      <table className="w-full text-left font-mono text-sm">
        <thead className="bg-terminal-bg text-terminal-dim text-xs border-b border-terminal-border">
          <tr>
            <th className="px-4 py-3 font-normal">FILENAME</th>
            <th className="px-4 py-3 font-normal">SIZE</th>
            <th className="px-4 py-3 font-normal">CHUNKS</th>
            <th className="px-4 py-3 font-normal">STATUS</th>
            <th className="px-4 py-3 font-normal">UPLOADED</th>
            <th className="px-4 py-3 font-normal text-right">ACTIONS</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-terminal-border">
          {files.map(file => {
            const isDegraded = file.status === 'degraded';
            const isLost = file.status === 'lost';
            
            let statusColor = 'text-terminal-green';
            if (isDegraded) statusColor = 'text-terminal-amber';
            if (isLost) statusColor = 'text-terminal-red';

            return (
              <tr key={file.file_id} className="hover:bg-terminal-border/30 transition-colors">
                <td className="px-4 py-3 text-gray-200 truncate max-w-[200px]" title={file.filename}>
                  {file.filename}
                </td>
                <td className="px-4 py-3 text-gray-200">{formatBytes(file.total_size)}</td>
                <td className="px-4 py-3 text-gray-200">{file.chunk_count}</td>
                <td className={`px-4 py-3 ${statusColor} relative group`}>
                  {file.status?.toUpperCase() || 'AVAILABLE'}
                  {isDegraded && (
                    <div className="absolute left-0 bottom-full mb-2 hidden group-hover:block w-48 bg-terminal-bg border border-terminal-border p-2 text-[10px] text-gray-300 z-10 shadow-lg">
                      1 replica offline — re-replication in progress
                    </div>
                  )}
                </td>
                <td className="px-4 py-3 text-terminal-dim">
                  {file.created_at ? new Date(file.created_at).toLocaleDateString() : '-'}
                </td>
                <td className="px-4 py-3 text-right">
                  <button 
                    onClick={() => downloadFile(file.file_id)}
                    className="text-terminal-cyan hover:text-white px-2 py-1 border border-terminal-cyan/30 hover:bg-terminal-cyan/10 transition-colors cursor-pointer text-xs"
                    disabled={isLost}
                    title={isLost ? "File lost" : "Download"}
                  >
                    ↓ DOWNLOAD
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export default FileTable;
