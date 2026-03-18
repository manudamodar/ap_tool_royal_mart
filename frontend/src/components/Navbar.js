import React, { useState, useEffect, useRef } from 'react';

const Navbar = ({ user, onLogout }) => {
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const profileRef = useRef(null);

  // Close profile popup when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (profileRef.current && !profileRef.current.contains(event.target)) {
        setIsProfileOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.addEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const msalData = user?.msal_data || {};

  // Use UI-Avatars to generate a profile picture from their name, as MSAL claims don't include the photo directly
  const displayName = user?.first_name || user?.username || "User";
  const profileImage = `https://ui-avatars.com/api/?name=${encodeURIComponent(displayName)}&background=f0f2f5&color=E31837&size=128&font-size=0.4&bold=true`;

  return (
    <nav style={{
      padding: '0.75rem 2rem',
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      backgroundColor: '#E31837',
      color: 'white',
      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
      position: 'relative',
      zIndex: 1000
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <h2 style={{ margin: 0, fontSize: '1.5rem', fontWeight: 'bold', letterSpacing: '1px' }}>
          AP Automation Portal
        </h2>
      </div>

      {user && (
        <div style={{ position: 'relative' }} ref={profileRef}>
          {/* Profile Trigger (Clickable) */}
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
              backgroundColor: isProfileOpen ? 'rgba(255, 255, 255, 0.2)' : 'transparent'
            }}
            onMouseOver={(e) => { e.currentTarget.style.backgroundColor = 'rgba(255, 255, 255, 0.2)'; }}
            onMouseOut={(e) => { e.currentTarget.style.backgroundColor = isProfileOpen ? 'rgba(255, 255, 255, 0.2)' : 'transparent'; }}
          >
            <div style={{ textAlign: 'right', lineHeight: '1.2' }}>
              <span style={{ fontSize: '15px', fontWeight: '600', color: 'white', display: 'block' }}>
                {displayName}
              </span>
            </div>

            <img
              src={profileImage}
              alt="Profile"
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '50%',
                border: '2px solid white',
                objectFit: 'cover',
                backgroundColor: 'white'
              }}
            />
          </div>

          {/* Profile Popup Menu / Sidebar Dropdown */}
          {isProfileOpen && (
            <div style={{
              position: 'absolute',
              top: 'calc(100% + 10px)',
              right: '0',
              backgroundColor: 'white',
              borderRadius: '8px',
              boxShadow: '0 8px 24px rgba(0,0,0,0.2)',
              width: '320px',
              color: '#333',
              overflow: 'hidden',
              display: 'flex',
              flexDirection: 'column',
              maxHeight: '80vh' // Keep it within screen
            }}>
              {/* Header inside popup */}
              <div style={{
                padding: '24px 20px',
                backgroundColor: '#f8f9fa',
                borderBottom: '1px solid #eee',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: '12px'
              }}>
                <img
                  src={profileImage}
                  alt="Large Profile"
                  style={{
                    width: '80px',
                    height: '80px',
                    borderRadius: '50%',
                    boxShadow: '0 4px 8px rgba(0,0,0,0.1)',
                    border: '3px solid white'
                  }}
                />
                <div style={{ textAlign: 'center' }}>
                  <h3 style={{ margin: 0, fontSize: '18px', color: '#111', fontWeight: 'bold' }}>
                    {displayName}
                  </h3>
                  <p style={{ margin: '4px 0 0 0', fontSize: '14px', color: '#666' }}>
                    {user.email}
                  </p>
                  <span style={{
                    display: 'inline-block',
                    marginTop: '8px',
                    padding: '4px 10px',
                    backgroundColor: '#ffe8e8',
                    color: '#E31837',
                    borderRadius: '12px',
                    fontSize: '12px',
                    fontWeight: 'bold',
                    textTransform: 'uppercase'
                  }}>
                    {user.role.replace(/_/g, ' ')}
                  </span>
                </div>
              </div>

              {/* Dynamic MSAL Details Section */}
              <div style={{ padding: '0', overflowY: 'auto', flex: 1 }}>
                <div style={{ padding: '16px 20px', borderBottom: '1px solid #eee', backgroundColor: '#fff' }}>
                  <h4 style={{ margin: '0 0 12px 0', fontSize: '13px', color: '#999', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Authentication Details
                  </h4>

                  {/* Map over MSAL data and display all string/number details */}
                  {Object.keys(msalData).length > 0 ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                      {Object.entries(msalData).map(([key, value]) => {
                        // Skip long tokens, internal hashes, or objects to keep the UI clean
                        if (typeof value !== 'string' && typeof value !== 'number') return null;
                        if (['aio', 'rh', 'uti', 'nonce', 'c_hash'].includes(key)) return null;

                        // Format the key to be more readable (e.g. preferred_username -> Preferred Username)
                        const formattedKey = key.replace(/([A-Z])/g, ' $1').replace(/_/g, ' ').replace(/^./, str => str.toUpperCase());

                        return (
                          <div key={key} style={{ display: 'flex', flexDirection: 'column' }}>
                            <span style={{ fontSize: '12px', color: '#777', fontWeight: '600' }}>{formattedKey}</span>
                            <span style={{ fontSize: '14px', color: '#222', wordBreak: 'break-all' }}>{value || 'N/A'}</span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <p style={{ fontSize: '13px', color: '#888', margin: 0 }}>No additional directory data available.</p>
                  )}
                </div>
              </div>

              {/* Logout Button */}
              <div style={{ padding: '16px 20px', backgroundColor: '#fafafa' }}>
                <button
                  onClick={onLogout}
                  style={{
                    width: '100%',
                    backgroundColor: 'white',
                    border: '1px solid #ddd',
                    color: '#E31837',
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
                    boxShadow: '0 1px 2px rgba(0,0,0,0.05)'
                  }}
                  onMouseOver={(e) => {
                    e.currentTarget.style.backgroundColor = '#fff5f5';
                    e.currentTarget.style.borderColor = '#ffcccc';
                  }}
                  onMouseOut={(e) => {
                    e.currentTarget.style.backgroundColor = 'white';
                    e.currentTarget.style.borderColor = '#ddd';
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
    </nav>
  );
};

export default Navbar;