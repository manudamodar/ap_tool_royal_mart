import React, { useEffect, useState } from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import LoginPage from './components/LoginPage';
import Dashboard from './components/Dashboard';
import { ThemeProvider } from './components/ThemeContext';

function App() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Check if the user is authenticated
    fetch('/api/auth/user/')
      .then(res => res.json())
      .then(data => {
        if (data.authenticated) {
          setUser(data);
        }
        setLoading(false);
      })
      .catch(err => {
        console.error("Error fetching user", err);
        setLoading(false);
      });
  }, []);

  const handleLogin = () => {
    window.location.href = '/api/auth/login/';
  };

  const handleLogout = () => {
    fetch('/api/auth/logout/', { method: 'POST' })
      .then(() => {
        setUser(null);
        window.location.href = '/';
      })
      .catch(err => {
        console.error("Logout failed", err);
        setUser(null);
        window.location.href = '/';
      });
  };

  return (
    <ThemeProvider>
      {loading ? (
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh', backgroundColor: 'var(--background-secondary)', color: 'var(--text-primary)' }}>
          <div style={{ fontSize: '1.2rem' }}>Loading...</div>
        </div>
      ) : (
        <Router>
          <div className="App" style={{ minHeight: '100vh', backgroundColor: 'var(--background-secondary)', fontFamily: "'Segoe UI', Roboto, Helvetica, Arial, sans-serif", color: 'var(--text-primary)' }}>
            <Navbar user={user} onLogout={handleLogout} />
            <main style={{ padding: '2rem', maxWidth: '1200px', margin: '0 auto' }}>
              <Routes>
                <Route path="/" element={
                  user ? <Dashboard user={user} /> : <LoginPage onLogin={handleLogin} />
                } />
              </Routes>
            </main>
          </div>
        </Router>
      )}
    </ThemeProvider>
  );
}

export default App;
