import React from 'react';

const Dashboard = ({ user }) => {
  const role = user.role;

  const handleAction = (actionName) => {
    // Placeholder for navigation or modal logic
    alert(`Action triggered: ${actionName}`);
  };

  const FeatureCard = ({ icon, title, description, onClick, isComingSoon, variant = 'default' }) => (
    <div
      onClick={!isComingSoon ? onClick : undefined}
      style={{
        backgroundColor: 'var(--card-background)',
        padding: '2rem',
        borderRadius: '8px',
        boxShadow: '0 2px 4px var(--shadow-color)',
        textAlign: 'center',
        border: '1px solid var(--card-border)',
        flex: 1,
        minWidth: '250px',
        color: 'var(--text-primary)',
        transition: 'all 0.3s',
        cursor: (!isComingSoon && onClick) ? 'pointer' : 'default',
        position: 'relative',
        opacity: isComingSoon ? 0.7 : 1,
        borderColor: variant === 'danger' ? '#ff4d4f' : variant === 'success' ? '#52c41a' : 'var(--card-border)'
      }}
      onMouseEnter={(e) => {
         if(!isComingSoon && onClick) {
             e.currentTarget.style.transform = 'translateY(-5px)';
             e.currentTarget.style.boxShadow = '0 8px 16px var(--shadow-color)';
         }
      }}
      onMouseLeave={(e) => {
         if(!isComingSoon && onClick) {
             e.currentTarget.style.transform = 'translateY(0)';
             e.currentTarget.style.boxShadow = '0 2px 4px var(--shadow-color)';
         }
      }}
    >
      {isComingSoon && (
        <span style={{
            position: 'absolute',
            top: '10px',
            right: '10px',
            backgroundColor: 'var(--text-secondary)',
            color: 'var(--card-background)',
            fontSize: '0.7rem',
            padding: '2px 6px',
            borderRadius: '4px',
            fontWeight: 'bold'
        }}>COMING SOON</span>
      )}
      <div style={{ fontSize: '2.5rem', marginBottom: '1rem', color: variant === 'danger' ? '#ff4d4f' : variant === 'success' ? '#52c41a' : 'var(--primary-accent)' }}>
        {icon}
      </div>
      <h3 style={{ marginBottom: '0.5rem', color: 'var(--text-primary)' }}>{title}</h3>
      <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>{description}</p>
    </div>
  );

  const renderContent = () => {
    switch (role) {
      case 'AP_TEAM':
        return (
          <div style={{ display: 'flex', gap: '2rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <FeatureCard
              icon="📂"
              title="View Payment Files"
              description="Access and review generated payment files."
              isComingSoon={true}
            />
          </div>
        );
      case 'STORE_ACCOUNTANT':
        return (
          <div style={{ display: 'flex', gap: '2rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <FeatureCard
              icon="📤"
              title="Upload Scanned Copy"
              description="Upload scanned invoice folders for processing."
              onClick={() => handleAction("Upload Scanned Copy")}
            />
            <FeatureCard
              icon="🧐"
              title="Verify / Manual Review"
              description="Review flagged invoices and edit payment details."
              onClick={() => handleAction("Manual Review")}
            />
            <FeatureCard
              icon="💳"
              title="Generate Payment File"
              description="Generate final payment files for approved invoices."
              isComingSoon={true}
            />
          </div>
        );
      case 'STORE_MANAGER':
        return (
          <div style={{ display: 'flex', gap: '2rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <FeatureCard
              icon="✅"
              title="Approve Payment File"
              description="Review and approve pending payment files."
              variant="success"
              onClick={() => handleAction("Approve Payment File")}
            />
            <FeatureCard
              icon="❌"
              title="Reject Payment File"
              description="Reject payment files that require correction."
              variant="danger"
              onClick={() => handleAction("Reject Payment File")}
            />
          </div>
        );
      default:
        // Default view for UNASSIGNED or unknown roles
        return (
          <div style={{ textAlign: 'center', color: 'var(--text-secondary)' }}>
             <h3>Welcome!</h3>
             <p>Your role ({role}) does not have specific actions assigned yet.</p>
             <p>Please contact your administrator if you believe this is an error.</p>
          </div>
        );
    }
  };

  return (
    <div style={{
        backgroundColor: 'var(--card-background)',
        padding: '3rem',
        borderRadius: '8px',
        boxShadow: '0 4px 6px var(--shadow-color)',
        color: 'var(--text-primary)',
        transition: 'background-color 0.3s, color 0.3s'
    }}>
      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
        <h1 style={{ marginBottom: '1rem', color: 'var(--text-primary)' }}>Welcome to Your Dashboard</h1>
        <p style={{ fontSize: '1.1rem', color: 'var(--text-secondary)' }}>
          You are logged in as a <strong>{user.role ? user.role.replace(/_/g, ' ') : 'User'}</strong>.
        </p>
      </div>

      {renderContent()}

      {/* Common section for all or maybe hidden for specific roles if needed */}
      <div style={{
        marginTop: '4rem',
        padding: '2rem',
        backgroundColor: 'var(--background-secondary)',
        border: '1px dashed var(--card-border)',
        borderRadius: '8px',
        textAlign: 'center'
      }}>
        <h2 style={{ marginBottom: '1rem', color: 'var(--text-primary)' }}>Activity Overview</h2>
        <p style={{ color: 'var(--text-secondary)' }}>
           Recent activity and status updates will appear here.
        </p>
      </div>
    </div>
  );
};

export default Dashboard;
