import React, { useState, useEffect, useRef } from 'react';
import { useTheme } from './ThemeContext';

const Navbar = ({ user, onLogout }) => {
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const profileRef = useRef(null);
  const { theme, toggleTheme } = useTheme();

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (profileRef.current && !profileRef.current.contains(event.target)) {
        setIsProfileOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const msalData = user?.msal_data || {};
  const displayName = user?.first_name || msalData.name || user?.username || "User";
  const email = user?.email || msalData.preferred_username || "N/A";
  const phoneNumber = msalData.mobilePhone || msalData.phoneNumber || msalData.mobile || "Not provided";
  const profileImage = user?.photo || `https://ui-avatars.com/api/?name=${encodeURIComponent(displayName)}&background=f0f2f5&color=E31837&size=128&font-size=0.4&bold=true`;

  return (
    <nav style={{
      padding: '0.75rem 2rem',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      backgroundColor: 'var(--navbar-background)',
      color: 'var(--text-primary)',
      boxShadow: '0 2px 4px var(--shadow-color)',
      position: 'relative',
      zIndex: 1000,
      borderBottom: '1px solid var(--card-border)',
      transition: 'background-color 0.3s, color 0.3s'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 'bold', letterSpacing: '1px', color: 'var(--primary-accent)' }}>
          AP Tool
        </h2>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
        <button onClick={toggleTheme} style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontSize: '1.2rem',
          padding: '5px',
          color: 'var(--text-primary)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }} title="Toggle Theme">
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>

        {user && (
          <div style={{ position: 'relative' }} ref={profileRef}>
            <div
              onClick={() => setIsProfileOpen(!isProfileOpen)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                cursor: 'pointer',
                padding: '6px 10px',
                borderRadius: '30px',
                transition: 'background-color 0.2s',
                backgroundColor: isProfileOpen ? 'var(--background-secondary)' : 'transparent',
                border: '1px solid var(--card-border)'
              }}
            >
              <div style={{ textAlign: 'right', lineHeight: '1.2' }}>
                <span style={{ fontSize: '15px', fontWeight: '600', color: 'var(--text-primary)', display: 'block' }}>
                  {displayName}
                </span>
              </div>
              <img
                src={profileImage}
                alt="Profile Avatar"
                style={{
                  width: '38px',
                  height: '38px',
                  borderRadius: '50%',
                  border: '2px solid var(--card-background)',
                  objectFit: 'cover',
                  backgroundColor: 'var(--background-secondary)'
                }}
              />
            </div>

            {isProfileOpen && (
              <div style={{
                position: 'absolute',
                top: 'calc(100% + 10px)',
                right: '0',
                backgroundColor: 'var(--card-background)',
                borderRadius: '8px',
                boxShadow: '0 8px 24px var(--shadow-color)',
                width: '300px',
                color: 'var(--text-primary)',
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                border: '1px solid var(--card-border)',
                zIndex: 1001
              }}>
                <div style={{
                  padding: '24px 20px',
                  backgroundColor: 'var(--background-secondary)',
                  borderBottom: '1px solid var(--card-border)',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '12px'
                }}>
                  <img
                    src={profileImage}
                    alt="Large Profile Avatar"
                    style={{
                      width: '80px',
                      height: '80px',
                      borderRadius: '50%',
                      boxShadow: '0 4px 8px var(--shadow-color)',
                      border: '3px solid var(--card-background)'
                    }}
                  />
                  <div style={{ textAlign: 'center' }}>
                    <h3 style={{ margin: 0, fontSize: '18px', color: 'var(--text-primary)', fontWeight: 'bold' }}>
                      {displayName}
                    </h3>
                    <span style={{
                      display: 'inline-block',
                      marginTop: '8px',
                      padding: '4px 10px',
                      backgroundColor: 'var(--primary-accent)',
                      color: '#ffffff', /* Always white text on accent background */
                      borderRadius: '12px',
                      fontSize: '12px',
                      fontWeight: 'bold',
                      textTransform: 'uppercase'
                    }}>
                      {user.role.replace(/_/g, ' ')}
                    </span>
                  </div>
                </div>

                <div style={{ padding: '20px', backgroundColor: 'var(--card-background)' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Email Address</span>
                      <span style={{ fontSize: '14px', color: 'var(--text-primary)', marginTop: '4px' }}>{email}</span>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 'bold', textTransform: 'uppercase', letterSpacing: '0.5px' }}>Mobile Number</span>
                      <span style={{ fontSize: '14px', color: 'var(--text-primary)', marginTop: '4px' }}>{phoneNumber}</span>
                    </div>
                  </div>
                </div>

                <div style={{ padding: '16px 20px', backgroundColor: 'var(--background-secondary)', borderTop: '1px solid var(--card-border)' }}>
                  <button
                    onClick={onLogout}
                    style={{
                      width: '100%',
                      backgroundColor: 'var(--card-background)',
                      border: '1px solid var(--card-border)',
                      color: 'var(--primary-accent)',
                      padding: '10px 16px',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      fontWeight: 'bold',
                      fontSize: '15px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px',
                      boxShadow: '0 1px 2px var(--shadow-color)'
                    }}
                  >
                    Sign Out
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </nav>
  );
};

export default Navbar;
