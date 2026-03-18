import React from 'react';

const LoginPage = ({ onLogin }) => {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      backgroundColor: 'white',
      padding: '4rem 2rem',
      borderRadius: '8px',
      boxShadow: '0 4px 6px rgba(0,0,0,0.05)',
      maxWidth: '500px',
      margin: '5rem auto', // Center the login box vertically
      textAlign: 'center'
    }}>
      <div style={{
        width: '80px',
        height: '80px',
        backgroundColor: '#f0f2f5',
        borderRadius: '50%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        marginBottom: '1.5rem'
      }}>
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#E31837" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"></path>
        </svg>
      </div>
      <h2 style={{ color: '#333', marginBottom: '1rem', fontSize: '1.8rem' }}>
        Secure Login
      </h2>
      <p style={{ color: '#666', marginBottom: '2.5rem', lineHeight: '1.5' }}>
        Access to the AP Automation Portal is restricted. Please sign in using your corporate Microsoft account.
      </p>

      <button
        onClick={onLogin}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '10px',
          backgroundColor: '#0078D4', // Microsoft Blue
          color: 'white',
          border: 'none',
          padding: '12px 24px',
          borderRadius: '4px',
          fontSize: '1rem',
          fontWeight: '600',
          cursor: 'pointer',
          width: '100%',
          boxShadow: '0 2px 4px rgba(0,120,212,0.3)',
          transition: 'background-color 0.2s'
        }}
        onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#005a9e'}
        onMouseOut={(e) => e.currentTarget.style.backgroundColor = '#0078D4'}
      >
        <svg width="20" height="20" viewBox="0 0 21 21" xmlns="http://www.w3.org/2000/svg">
          <rect x="1" y="1" width="9" height="9" fill="#f25022"/>
          <rect x="11" y="1" width="9" height="9" fill="#7fba00"/>
          <rect x="1" y="11" width="9" height="9" fill="#00a4ef"/>
          <rect x="11" y="11" width="9" height="9" fill="#ffb900"/>
        </svg>
        Sign in with Microsoft
      </button>
    </div>
  );
};

export default LoginPage;
