import React from 'react';

const Dashboard = ({ user }) => {
  // A simple placeholder for a feature card
  const FeatureCard = ({ icon, title, description }) => (
    <div style={{
      backgroundColor: '#fff',
      padding: '2rem',
      borderRadius: '8px',
      boxShadow: '0 2px 4px rgba(0,0,0,0.05)',
      textAlign: 'center',
      border: '1px solid #eee',
      flex: 1,
      minWidth: '250px',
    }}>
      <div style={{ fontSize: '2.5rem', marginBottom: '1rem', color: '#E31837' }}>
        {icon}
      </div>
      <h3 style={{ color: '#333', marginBottom: '0.5rem' }}>{title}</h3>
      <p style={{ color: '#666', fontSize: '0.9rem' }}>{description}</p>
    </div>
  );

  return (
    <div style={{ backgroundColor: 'white', padding: '3rem', borderRadius: '8px', boxShadow: '0 4px 6px rgba(0,0,0,0.05)' }}>
      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
        <h1 style={{ color: '#333', marginBottom: '1rem' }}>Welcome to Your Dashboard</h1>
        <p style={{ fontSize: '1.1rem', color: '#666' }}>
          You are logged in as a <strong>{user.role.replace('_', ' ')}</strong>.
        </p>
      </div>

      {/* Feature Section */}
      <div style={{ display: 'flex', gap: '2rem', justifyContent: 'center', flexWrap: 'wrap' }}>
        <FeatureCard
          icon="📄"
          title="Upload Invoices"
          description="Start by uploading new vendor invoices for processing."
        />
        <FeatureCard
          icon="📊"
          title="View Reports"
          description="Analyze processed data and generate financial reports."
        />
        <FeatureCard
          icon="⚙️"
          title="Manage Settings"
          description="Configure your profile and application settings."
        />
      </div>

      {/* Placeholder for future content */}
      <div style={{
        marginTop: '4rem',
        padding: '2rem',
        backgroundColor: '#f9f9f9',
        border: '1px dashed #ddd',
        borderRadius: '8px',
        textAlign: 'center'
      }}>
        <h2 style={{ color: '#555', marginBottom: '1rem' }}>Invoice Data Table</h2>
        <p style={{ color: '#777' }}>
          A table displaying invoice data will be available here soon.
        </p>
      </div>
    </div>
  );
};

export default Dashboard;
