import React, { useState, useEffect, useRef } from 'react';
import { useTheme } from './ThemeContext';

const Navbar = ({ user, onLogout }) => {
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const profileRef = useRef(null);
  const { theme, toggleTheme } = useTheme();

  // Local state to manage the role shown in the navbar dropdown
  const [currentRole, setCurrentRole] = useState(user?.role || 'UNASSIGNED');

  // Keep it synced if the main user prop changes
  useEffect(() => {
    if (user?.role) {
      setCurrentRole(user.role);
    }
  }, [user]);

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

  const handleRoleChange = async (e) => {
    const newRole = e.target.value;
    try {
        const response = await fetch('/api/auth/change_role/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: newRole })
        });
        if(response.ok) {
            setCurrentRole(newRole);
            // Dispatch a custom event so the Dashboard knows the role changed
            const event = new CustomEvent('userRoleChanged', { detail: { newRole } });
            window.dispatchEvent(event);
        } else {
            alert("Failed to change role.");
        }
    } catch(err) {
        console.error("Error changing role:", err);
    }
  };

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
      boxShadow: 'var(--shadow-sm)',
      position: 'sticky',
      top: 0,
      zIndex: 1000,
      borderBottom: '1px solid var(--card-border)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <div style={{
          width: '32px',
          height: '32px',
          backgroundColor: 'var(--primary-accent)',
          borderRadius: '6px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'white',
          fontWeight: 'bold',
          fontSize: '18px'
        }}>
          A
        </div>
        <h2 style={{ margin: 0, fontSize: '1.25rem', fontWeight: '700', letterSpacing: '-0.5px' }}>
          AP Automation
        </h2>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        {/* Modern Theme Toggle using SVGs instead of emojis */}
        <button
          onClick={toggleTheme}
          style={{
            background: 'var(--background-secondary)',
            border: '1px solid var(--card-border)',
            cursor: 'pointer',
            padding: '8px',
            borderRadius: '50%',
            color: 'var(--text-primary)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transition: 'all 0.2s ease',
            width: '36px',
            height: '36px'
          }}
          title="Toggle Theme"
        >
          {theme === 'dark' ? (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5"></circle>
              <line x1="12" y1="1" x2="12" y2="3"></line>
              <line x1="12" y1="21" x2="12" y2="23"></line>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line>
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line>
              <line x1="1" y1="12" x2="3" y2="12"></line>
              <line x1="21" y1="12" x2="23" y2="12"></line>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line>
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>
            </svg>
          ) : (
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>
            </svg>
          )}
        </button>

        {user && (
          <div style={{ position: 'relative' }} ref={profileRef}>
            <div
              onClick={() => setIsProfileOpen(!isProfileOpen)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '10px',
                cursor: 'pointer',
                padding: '4px 6px',
                borderRadius: '30px',
                transition: 'background-color 0.2s',
                backgroundColor: isProfileOpen ? 'var(--background-secondary)' : 'transparent',
                border: '1px solid transparent',
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--background-secondary)'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = isProfileOpen ? 'var(--background-secondary)' : 'transparent'}
            >
              <div style={{ textAlign: 'right', lineHeight: '1.1', display: 'none' /* Hide name on small screens, adjust with media queries if using standard CSS */ }}>
                 {/* Name kept for structure, hidden to make UI cleaner like modern apps, rely on avatar */}
              </div>
              <img
                src={profileImage}
                alt="Profile"
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '50%',
                  border: '2px solid var(--card-border)',
                  objectFit: 'cover',
                }}
              />
            </div>

            {isProfileOpen && (
              <div style={{
                position: 'absolute',
                top: 'calc(100% + 12px)',
                right: '0',
                backgroundColor: 'var(--card-background)',
                borderRadius: '12px',
                boxShadow: 'var(--shadow-lg)',
                width: '320px',
                color: 'var(--text-primary)',
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column',
                border: '1px solid var(--card-border)',
                zIndex: 1001,
                animation: 'fadeIn 0.2s ease-out'
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
                    alt="Large Profile"
                    style={{
                      width: '72px',
                      height: '72px',
                      borderRadius: '50%',
                      boxShadow: 'var(--shadow-md)',
                      border: '3px solid var(--card-background)'
                    }}
                  />
                  <div style={{ textAlign: 'center', width: '100%' }}>
                    <h3 style={{ margin: 0, fontSize: '18px', color: 'var(--text-primary)', fontWeight: '600' }}>
                      {displayName}
                    </h3>
                    <p style={{ margin: '4px 0 12px 0', fontSize: '14px', color: 'var(--text-secondary)' }}>
                       {email}
                    </p>

                    {/* --- FOR TESTING: User Role Dropdown --- */}
                    <div style={{
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: '4px',
                      marginTop: '8px'
                    }}>
                        <span style={{ fontSize: '11px', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 'bold' }}>
                            Simulated Role (Testing)
                        </span>
                        <select
                            value={currentRole}
                            onChange={handleRoleChange}
                            style={{
                                padding: '4px 8px',
                                borderRadius: '16px',
                                border: '1px solid var(--primary-accent)',
                                backgroundColor: 'var(--primary-accent-light)',
                                color: 'var(--primary-accent)',
                                fontSize: '12px',
                                fontWeight: '600',
                                outline: 'none',
                                cursor: 'pointer',
                                textAlign: 'center',
                                appearance: 'none', // removes default OS styling arrow
                                WebkitAppearance: 'none',
                                MozAppearance: 'none',
                            }}
                        >
                            <option value="UNASSIGNED">UNASSIGNED</option>
                            <option value="STORE_ACCOUNTANT">STORE ACCOUNTANT</option>
                            <option value="STORE_MANAGER">STORE MANAGER</option>
                            <option value="AP_TEAM">AP TEAM</option>
                        </select>
                    </div>
                    {/* -------------------------------------- */}

                  </div>
                </div>

                {phoneNumber !== "Not provided" && (
                  <div style={{ padding: '20px', backgroundColor: 'var(--card-background)' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: '600', textTransform: 'uppercase' }}>Mobile Number</span>
                        <span style={{ fontSize: '14px', color: 'var(--text-primary)' }}>{phoneNumber}</span>
                    </div>
                  </div>
                )}

                <div style={{ padding: '12px', backgroundColor: 'var(--background-secondary)', borderTop: '1px solid var(--card-border)' }}>
                  <button
                    onClick={onLogout}
                    style={{
                      width: '100%',
                      backgroundColor: 'transparent',
                      border: '1px solid var(--card-border)',
                      color: 'var(--text-primary)',
                      padding: '10px 16px',
                      borderRadius: '8px',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      fontWeight: '500',
                      fontSize: '14px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: '8px',
                    }}
                    onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor = 'var(--danger-bg)';
                        e.currentTarget.style.color = 'var(--danger)';
                        e.currentTarget.style.borderColor = 'transparent';
                    }}
                    onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = 'transparent';
                        e.currentTarget.style.color = 'var(--text-primary)';
                        e.currentTarget.style.borderColor = 'var(--card-border)';
                    }}
                  >
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
                      <polyline points="16 17 21 12 16 7"></polyline>
                      <line x1="21" y1="12" x2="9" y2="12"></line>
                    </svg>
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