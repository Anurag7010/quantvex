import React from "react";
import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import { HomePage, ChatPage, DashboardPage } from "./pages";
import { ThemeProvider } from "./context/ThemeContext";
import ErrorBoundary from "./ErrorBoundary";

function App() {
  return (
    <ThemeProvider>
      <Router>
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
          </Routes>
        </ErrorBoundary>
      </Router>
    </ThemeProvider>
  );
}

export default App;
