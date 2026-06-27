import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout';
import Cluster from './pages/Cluster';
import Tasks from './pages/Tasks';
import Storage from './pages/Storage';
import Functions from './pages/Functions';
import Logs from './pages/Logs';

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/cluster" replace />} />
          <Route path="cluster" element={<Cluster />} />
          <Route path="tasks" element={<Tasks />} />
          <Route path="storage" element={<Storage />} />
          <Route path="functions" element={<Functions />} />
          <Route path="logs" element={<Logs />} />
          <Route path="*" element={<Navigate to="/cluster" replace />} />
        </Route>
      </Routes>
    </Router>
  );
}

export default App;
