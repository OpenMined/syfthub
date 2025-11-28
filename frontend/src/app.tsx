import React from 'react';

import { BrowserRouter, Route, Routes } from 'react-router-dom';

import { MainApp } from './components/main-app';
import RootProvider from './components/providers/root';
import { AuthProvider } from './context/auth-context';

export default function App() {
  return (
    <RootProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path='/*' element={<MainApp />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </RootProvider>
  );
}
