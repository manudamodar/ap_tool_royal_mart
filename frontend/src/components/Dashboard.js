import React, { useRef, useState, useEffect } from 'react';

const Dashboard = ({ user }) => {
  const [role, setRole] = useState(user.role);
  const fileInputRef = useRef(null);

  // State for tracking upload progress
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);

  // State for tracking processing status
  const [activeBatchId, setActiveBatchId] = useState(null);
  const [batchStatus, setBatchStatus] = useState(null);
  const [batchData, setBatchData] = useState(null);

  // State for Activity Overview list with Pagination
  const [recentBatches, setRecentBatches] = useState([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [isFetchingBatches, setIsFetchingBatches] = useState(false);

  // State for Document Modal
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [isFetchingDocument, setIsFetchingDocument] = useState(false);

  const [notification, setNotification] = useState(null); // { message, type }

  // Use a ref to track if we already showed the scanning toast for a specific batch to prevent double-firing
  const scanningToastShownRef = useRef(null);

  useEffect(() => {
    fetchRecentBatches(currentPage);
  }, [role, currentPage]);

  useEffect(() => {
    const handleRoleUpdate = (event) => {
      setRole(event.detail.newRole);
      setCurrentPage(1);
    };
    window.addEventListener('userRoleChanged', handleRoleUpdate);
    return () => {
      window.removeEventListener('userRoleChanged', handleRoleUpdate);
    };
  }, []);

  // Clear notification after 3 seconds
  useEffect(() => {
      if (notification) {
          const timer = setTimeout(() => setNotification(null), 3000);
          return () => clearTimeout(timer);
      }
  }, [notification]);

  const showNotification = (message, type = 'success') => {
      setNotification({ message, type });
  };

  const fetchRecentBatches = async (pageToFetch = 1) => {
    setIsFetchingBatches(true);
    try {
      const response = await fetch(`/api/ocr/batches/?page=${pageToFetch}&limit=5`);
      const data = await response.json();
      if (response.ok) {
        setRecentBatches(data.batches || []);
        if (data.pagination) {
            setTotalPages(data.pagination.total_pages);
            setCurrentPage(data.pagination.current_page);
        }
      }
    } catch (error) {
      console.error("Error fetching recent batches:", error);
    } finally {
        setIsFetchingBatches(false);
    }
  };

  const handlePageChange = (newPage) => {
      if (newPage >= 1 && newPage <= totalPages) {
          setCurrentPage(newPage);
      }
  };

  const handleAction = (actionName) => {
    if (actionName === "Upload Scanned Copy") {
      fileInputRef.current.click();
    } else {
      showNotification(`Action Triggered: ${actionName}`, "info");
    }
  };

  const onFilesSelected = (event) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;

    // Execute upload directly when files are selected
    executeFolderUpload(files);
  };

  const executeFolderUpload = async (files) => {
    setIsUploading(true);
    setUploadProgress(0);
    setBatchStatus(null);
    setBatchData(null);

    const formData = new FormData();

    Array.from(files).forEach((file) => {
      formData.append('files', file);
    });

    try {
      const xhr = new XMLHttpRequest();

      xhr.upload.addEventListener("progress", (event) => {
          if (event.lengthComputable) {
              const percentComplete = Math.round((event.loaded / event.total) * 100);
              setUploadProgress(percentComplete);
          }
      });

      const uploadPromise = new Promise((resolve, reject) => {
          xhr.addEventListener("load", () => {
              if (xhr.status >= 200 && xhr.status < 300) {
                  try {
                      resolve({ ok: true, status: xhr.status, data: JSON.parse(xhr.responseText) });
                  } catch (e) {
                      resolve({ ok: true, status: xhr.status, data: {} });
                  }
              } else {
                  try {
                      resolve({ ok: false, status: xhr.status, data: JSON.parse(xhr.responseText) });
                  } catch (e) {
                      resolve({ ok: false, status: xhr.status, data: { error: "Upload failed" } });
                  }
              }
          });
          xhr.addEventListener("error", () => reject(new Error("Network Error")));
          xhr.addEventListener("abort", () => reject(new Error("Upload Aborted")));
      });

      xhr.open("POST", "/api/ocr/upload/");
      xhr.send(formData);

      const response = await uploadPromise;

      if (response.status === 202) {
        // Immediately show the toast as soon as we get the 202 response
        showNotification("File upload done! Background processing started.", "success");

        setActiveBatchId(response.data.batch_id);
        setCurrentPage(1);
        fetchRecentBatches(1);

        setUploadProgress(0);
        setBatchStatus('PENDING');
      } else {
        showNotification(response.data.error || 'Upload failed', "error");
      }
    } catch (error) {
      console.error("Error uploading folder:", error);
      showNotification("An error occurred during upload. Check your network connection.", "error");
    }

    setIsUploading(false);
    if (fileInputRef.current) {
       fileInputRef.current.value = null;
    }
  };

  // Polling logic for active batch
  useEffect(() => {
    let pollInterval;

    if (activeBatchId && (!batchStatus || (batchStatus !== 'INVOICES_SCANNED' && batchStatus !== 'FAILED' && batchStatus !== 'MANUAL_REVIEW')) && !isUploading) {
      pollInterval = setInterval(async () => {
        try {
          const response = await fetch(`/api/ocr/status/${activeBatchId}/`);
          const data = await response.json();

          if (response.ok) {
            // Check ref to ensure we ONLY show this once per batch ID
            if (data.status === 'INVOICES_SCANNING_IN_PROCESS' && scanningToastShownRef.current !== activeBatchId) {
                showNotification("Invoices scanning in process...", "info");
                scanningToastShownRef.current = activeBatchId;
            }

            setBatchStatus(data.status);

            if (data.total_files > 0) {
               setUploadProgress(Math.round((data.processed_files / data.total_files) * 100));
            }

            if (data.status === 'INVOICES_SCANNED' || data.status === 'FAILED' || data.status === 'MANUAL_REVIEW' || data.status === 'COMPLETED') {
              clearInterval(pollInterval);
              if (data.status === 'INVOICES_SCANNED' || data.status === 'COMPLETED') {
                 setBatchData(data.results);
                 fetchRecentBatches(currentPage);
                 showNotification("Batch processing complete! All documents verified.", "success");
              } else if (data.status === 'MANUAL_REVIEW') {
                 setBatchData(data.results);
                 fetchRecentBatches(currentPage);
                 showNotification("Batch processed, but some documents require manual review.", "warning");
              } else {
                 showNotification("Batch processing failed.", "error");
              }
            }
          }
        } catch (error) {
          console.error("Error polling batch status:", error);
        }
      }, 2000);
    }

    return () => {
      if (pollInterval) clearInterval(pollInterval);
    };
  }, [activeBatchId, batchStatus, currentPage, isUploading]);

  const handleBatchClick = async (batchId, status) => {
      setActiveBatchId(batchId);
      setBatchStatus(status);

      if (status === 'INVOICES_SCANNED' || status === 'MANUAL_REVIEW' || status === 'COMPLETED') { // Added COMPLETED to be safe, though model uses INVOICES_SCANNED usually, tasks uses COMPLETED
          try {
              const response = await fetch(`/api/ocr/status/${batchId}/`);
              const data = await response.json();
              if (response.ok) {
                  setBatchData(data.results);
                  setUploadProgress(100);
              }
          } catch (e) {
              console.error("Failed to load batch details");
              showNotification("Failed to load details", "error");
          }
      } else {
          setBatchData(null);
          setUploadProgress(0);
      }
  };

  const handleDocumentClick = async (documentId) => {
      setIsFetchingDocument(true);
      try {
          const response = await fetch(`/api/ocr/document/${documentId}/`);
          const data = await response.json();
          if (response.ok) {
              setSelectedDocument(data);
          } else {
              showNotification(data.error || "Failed to fetch document details.", "error");
          }
      } catch (error) {
          console.error("Error fetching document details:", error);
          showNotification("An error occurred while fetching document details.", "error");
      } finally {
          setIsFetchingDocument(false);
      }
  };

  const closeDocumentModal = () => {
      setSelectedDocument(null);
  };


  /* --- UI COMPONENTS --- */

  const ToastNotification = () => {
      if (!notification) return null;

      const isError = notification.type === 'error';
      const isInfo = notification.type === 'info';
      const isWarning = notification.type === 'warning';

      let bgColor = 'var(--success)';
      if (isError) bgColor = 'var(--danger)';
      if (isInfo) bgColor = 'var(--primary-accent)';
      if (isWarning) bgColor = '#faad14'; // Orange/Yellow

      return (
          <div style={{
              position: 'fixed', bottom: '24px', right: '24px', zIndex: 9998,
              backgroundColor: bgColor,
              color: 'white', padding: '12px 20px', borderRadius: '8px',
              boxShadow: 'var(--shadow-md)', fontWeight: '500',
              display: 'flex', alignItems: 'center', gap: '8px',
              animation: 'slideUp 0.3s ease-out'
          }}>
              {isError ? (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>
              ) : isInfo ? (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
              ) : isWarning ? (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
              )}
              {notification.message}
          </div>
      );
  };

  const FeatureCard = ({ iconSvg, title, description, onClick, isComingSoon, variant = 'default' }) => (
    <div
      onClick={!isComingSoon && !isUploading ? onClick : undefined}
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
        cursor: (!isComingSoon && onClick && !isUploading) ? 'pointer' : 'default',
        position: 'relative',
        opacity: (isComingSoon || (isUploading && title === "Upload Scanned Copy")) ? 0.7 : 1,
        borderColor: variant === 'danger' ? '#ff4d4f' : variant === 'success' ? '#52c41a' : 'var(--card-border)'
      }}
      onMouseEnter={(e) => {
         if(!isComingSoon && onClick && !isUploading) {
             e.currentTarget.style.transform = 'translateY(-5px)';
             e.currentTarget.style.boxShadow = '0 8px 16px var(--shadow-color)';
         }
      }}
      onMouseLeave={(e) => {
         if(!isComingSoon && onClick && !isUploading) {
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

      <div style={{
          marginBottom: '1rem',
          display: 'flex',
          justifyContent: 'center',
          color: variant === 'danger' ? '#ff4d4f' : variant === 'success' ? '#52c41a' : 'var(--primary-accent)'
      }}>
        {iconSvg}
      </div>
      <h3 style={{ marginBottom: '0.5rem', color: 'var(--text-primary)' }}>{title}</h3>
      <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
        {description}
      </p>

      {/* Embedded Upload Progress Bar in the Card */}
      {isUploading && title === "Upload Scanned Copy" && (
          <div style={{ marginTop: '15px' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--primary-accent)', fontWeight: 'bold', marginBottom: '4px' }}>
                  {uploadProgress === 100 ? "File upload done!" : `Uploading Files: ${uploadProgress}%`}
              </div>
              <div style={{ width: '100%', height: '6px', backgroundColor: 'var(--background-secondary)', borderRadius: '3px', overflow: 'hidden' }}>
                  <div style={{ width: `${uploadProgress}%`, height: '100%', backgroundColor: 'var(--primary-accent)', transition: 'width 0.2s' }}></div>
              </div>
          </div>
      )}
    </div>
  );

  // SVG Icons
  const FolderIcon = (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
    </svg>
  );

  const UploadIcon = (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
      <polyline points="17 8 12 3 7 8"></polyline>
      <line x1="12" y1="3" x2="12" y2="15"></line>
    </svg>
  );

  const ReviewIcon = (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
      <polyline points="14 2 14 8 20 8"></polyline>
      <line x1="16" y1="13" x2="8" y2="13"></line>
      <line x1="16" y1="17" x2="8" y2="17"></line>
      <polyline points="10 9 9 9 8 9"></polyline>
    </svg>
  );

  const PaymentIcon = (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect>
      <line x1="1" y1="10" x2="23" y2="10"></line>
    </svg>
  );

  const ApproveIcon = (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
      <polyline points="22 4 12 14.01 9 11.01"></polyline>
    </svg>
  );

  const RejectIcon = (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"></circle>
      <line x1="15" y1="9" x2="9" y2="15"></line>
      <line x1="9" y1="9" x2="15" y2="15"></line>
    </svg>
  );

  const formatStatus = (statusStr) => {
      if(!statusStr) return '';
      return statusStr.replace(/_/g, ' ');
  };

  const formatDate = (dateStr) => {
      if(!dateStr) return '';
      return new Date(dateStr).toLocaleString();
  };

  const getStatusColor = (status) => {
      switch (status) {
          case 'INVOICES_SCANNED':
          case 'COMPLETED': // Sometimes the task sets it to this
          case 'VERIFIED':
              return { bg: 'var(--success-bg)', text: 'var(--success)' };
          case 'FAILED':
          case 'NO_MATCH':
              return { bg: 'var(--danger-bg)', text: 'var(--danger)' };
          case 'MANUAL_REVIEW':
              return { bg: '#fffbe6', text: '#faad14' }; // Warning orange/yellow
          default:
              return { bg: 'var(--primary-accent-light)', text: 'var(--primary-accent)' };
      }
  };

  const renderContent = () => {
    switch (role) {
      case 'AP_TEAM':
        return (
          <div style={{ display: 'flex', gap: '2rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <FeatureCard
              iconSvg={FolderIcon}
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
              iconSvg={UploadIcon}
              title="Upload Scanned Copy"
              description="Select a folder containing scanned invoice copies (PDFs, Images)."
              onClick={() => handleAction("Upload Scanned Copy")}
            />
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              webkitdirectory="true"
              directory="true"
              multiple
              onChange={onFilesSelected}
            />

            <FeatureCard
              iconSvg={ReviewIcon}
              title="Verify / Manual Review"
              description="Review flagged invoices and edit payment details."
              isComingSoon={true}
              onClick={() => handleAction("Manual Review")}
            />
            <FeatureCard
              iconSvg={PaymentIcon}
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
              iconSvg={ApproveIcon}
              title="Approve Payment File"
              description="Review and approve pending payment files."
              variant="success"
              onClick={() => handleAction("Approve Payment File")}
            />
            <FeatureCard
              iconSvg={RejectIcon}
              title="Reject Payment File"
              description="Reject payment files that require correction."
              variant="danger"
              onClick={() => handleAction("Reject Payment File")}
            />
          </div>
        );
      default:
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
        transition: 'background-color 0.3s, color 0.3s',
        position: 'relative' // For absolute dialogs
    }}>
      <ToastNotification />

      <div style={{ textAlign: 'center', marginBottom: '3rem' }}>
        <h1 style={{ marginBottom: '1rem', color: 'var(--text-primary)' }}>Welcome to Your Dashboard</h1>
      </div>

      {renderContent()}

      <div style={{
        marginTop: '4rem',
        display: 'flex',
        gap: '2rem',
        flexDirection: 'column'
      }}>

        {/* Activity List Section */}
        <div style={{
            padding: '2rem',
            backgroundColor: 'var(--background-secondary)',
            border: '1px solid var(--card-border)',
            borderRadius: '8px',
        }}>
            <h2 style={{ marginBottom: '1.5rem', color: 'var(--text-primary)', fontSize: '1.2rem' }}>Recent Upload Batches</h2>

            {isFetchingBatches && recentBatches.length === 0 ? (
                <p style={{ color: 'var(--text-secondary)', textAlign: 'center' }}>Loading...</p>
            ) : recentBatches.length === 0 ? (
                <p style={{ color: 'var(--text-secondary)', textAlign: 'center', fontStyle: 'italic' }}>No batches uploaded yet.</p>
            ) : (
                <>
                  <div style={{ overflowX: 'auto', minHeight: '300px' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                          <thead>
                              <tr style={{ borderBottom: '2px solid var(--card-border)' }}>
                                  <th style={{ padding: '10px', color: 'var(--text-secondary)', fontWeight: '600' }}>Batch ID</th>
                                  <th style={{ padding: '10px', color: 'var(--text-secondary)', fontWeight: '600' }}>Date & Time</th>
                                  <th style={{ padding: '10px', color: 'var(--text-secondary)', fontWeight: '600' }}>Files</th>
                                  <th style={{ padding: '10px', color: 'var(--text-secondary)', fontWeight: '600' }}>Status</th>
                              </tr>
                          </thead>
                          <tbody style={{ opacity: isFetchingBatches ? 0.5 : 1, transition: 'opacity 0.2s' }}>
                              {recentBatches.map(batch => {
                                  const colors = getStatusColor(batch.status);
                                  return (
                                  <tr
                                      key={batch.batch_id}
                                      onClick={() => handleBatchClick(batch.batch_id, batch.status)}
                                      style={{
                                          borderBottom: '1px solid var(--card-border)',
                                          cursor: 'pointer',
                                          backgroundColor: activeBatchId === batch.batch_id ? 'var(--card-background)' : 'transparent',
                                          transition: 'background-color 0.2s'
                                      }}
                                      onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--card-background)'}
                                      onMouseLeave={(e) => e.currentTarget.style.backgroundColor = activeBatchId === batch.batch_id ? 'var(--card-background)' : 'transparent'}
                                  >
                                      <td style={{ padding: '12px 10px', fontFamily: 'monospace', fontSize: '0.9rem', color: 'var(--primary-accent)' }}>
                                          {batch.batch_id}
                                      </td>
                                      <td style={{ padding: '12px 10px', fontSize: '0.9rem' }}>{formatDate(batch.created_at)}</td>
                                      <td style={{ padding: '12px 10px', fontSize: '0.9rem' }}>{batch.processed_files} / {batch.total_files}</td>
                                      <td style={{ padding: '12px 10px', fontSize: '0.85rem', fontWeight: 'bold' }}>
                                          <span style={{
                                              padding: '4px 8px',
                                              borderRadius: '12px',
                                              backgroundColor: colors.bg,
                                              color: colors.text
                                          }}>
                                              {formatStatus(batch.status)}
                                          </span>
                                      </td>
                                  </tr>
                              )})}
                          </tbody>
                      </table>
                  </div>

                  {/* Pagination Controls */}
                  {totalPages > 1 && (
                    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '15px', marginTop: '20px', paddingTop: '15px', borderTop: '1px solid var(--card-border)' }}>
                        <button
                          onClick={() => handlePageChange(currentPage - 1)}
                          disabled={currentPage === 1 || isFetchingBatches}
                          style={{
                              padding: '6px 12px',
                              backgroundColor: (currentPage === 1 || isFetchingBatches) ? 'var(--background-secondary)' : 'var(--card-background)',
                              color: (currentPage === 1 || isFetchingBatches) ? 'var(--text-secondary)' : 'var(--text-primary)',
                              border: '1px solid var(--card-border)',
                              cursor: (currentPage === 1 || isFetchingBatches) ? 'not-allowed' : 'pointer',
                          }}
                        >
                            Previous
                        </button>

                        <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                            Page <strong style={{ color: 'var(--text-primary)' }}>{currentPage}</strong> of <strong>{totalPages}</strong>
                        </span>

                        <button
                          onClick={() => handlePageChange(currentPage + 1)}
                          disabled={currentPage === totalPages || isFetchingBatches}
                          style={{
                              padding: '6px 12px',
                              backgroundColor: (currentPage === totalPages || isFetchingBatches) ? 'var(--background-secondary)' : 'var(--card-background)',
                              color: (currentPage === totalPages || isFetchingBatches) ? 'var(--text-secondary)' : 'var(--text-primary)',
                              border: '1px solid var(--card-border)',
                              cursor: (currentPage === totalPages || isFetchingBatches) ? 'not-allowed' : 'pointer',
                          }}
                        >
                            Next
                        </button>
                    </div>
                  )}
                </>
            )}
        </div>

        {/* Dynamic Detail View for Selected Batch */}
        {activeBatchId && (
          <div style={{ padding: '2rem', backgroundColor: 'var(--card-background)', borderRadius: '8px', boxShadow: '0 2px 4px var(--shadow-color)', border: '1px solid var(--card-border)' }}>
            <h3 style={{ marginTop: 0, color: 'var(--primary-accent)', fontSize: '1.1rem' }}>Batch Details: {activeBatchId}</h3>

            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.9rem' }}>
              <span style={{ fontWeight: 'bold', color: 'var(--text-primary)' }}>Status: <span style={{ color: getStatusColor(batchStatus).text}}>{formatStatus(batchStatus)}</span></span>

              {/* If uploading to server, we don't show the processing progress here yet */}
              {!isUploading && (
                  <span style={{ color: 'var(--text-secondary)' }}>{uploadProgress}%</span>
              )}
            </div>

            {/* Processing Progress Bar */}
            {!isUploading && (
                <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--background-secondary)', borderRadius: '4px', overflow: 'hidden', marginBottom: '1rem' }}>
                  <div style={{
                    height: '100%',
                    width: `${uploadProgress}%`,
                    backgroundColor: batchStatus === 'FAILED' ? 'var(--danger)' : (batchStatus === 'INVOICES_SCANNED' || batchStatus === 'MANUAL_REVIEW' || batchStatus === 'COMPLETED') ? 'var(--success)' : 'var(--primary-accent)',
                    transition: 'width 0.5s ease'
                  }} />
                </div>
            )}

            {(batchStatus === 'INVOICES_SCANNED' || batchStatus === 'MANUAL_REVIEW' || batchStatus === 'COMPLETED') && batchData && (
              <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--card-border)', paddingTop: '1rem' }}>
                <h4 style={{ color: batchStatus === 'MANUAL_REVIEW' ? '#faad14' : 'var(--success)', marginBottom: '0.5rem' }}>
                    {batchStatus === 'MANUAL_REVIEW' ? 'Processing Complete (Review Needed)' : 'Processing Complete!'}
                </h4>
                <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '1rem' }}>Extracted {batchData.length} documents.</p>

                <div style={{ maxHeight: '400px', overflowY: 'auto', paddingRight: '10px' }}>
                  {batchData.map((doc) => {
                     const docColors = getStatusColor(doc.reconciliation_status);
                     return (
                    <div
                      key={doc.id}
                      onClick={() => handleDocumentClick(doc.id)}
                      style={{
                          padding: '1rem',
                          border: '1px solid var(--card-border)',
                          borderRadius: '6px',
                          marginBottom: '0.75rem',
                          backgroundColor: 'var(--background-secondary)',
                          cursor: 'pointer',
                          transition: 'border-color 0.2s',
                          borderLeft: `4px solid ${docColors.text}`
                      }}
                      onMouseEnter={(e) => e.currentTarget.style.borderColor = 'var(--primary-accent)'}
                      onMouseLeave={(e) => e.currentTarget.style.borderColor = 'var(--card-border)'}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                          <strong style={{ fontSize: '0.95rem', color: 'var(--text-primary)' }}>{doc.filename}</strong>
                          <span style={{
                              fontSize: '0.75rem',
                              fontWeight: 'bold',
                              padding: '2px 8px',
                              borderRadius: '10px',
                              backgroundColor: docColors.bg,
                              color: docColors.text
                          }}>
                              {formatStatus(doc.reconciliation_status)}
                          </span>
                      </div>

                      {doc.reconciliation_status !== 'VERIFIED' && doc.reconciliation_details && doc.reconciliation_details.message && (
                          <div style={{ fontSize: '0.85rem', color: 'var(--danger)', marginBottom: '8px', padding: '4px', backgroundColor: 'var(--danger-bg)', borderRadius: '4px' }}>
                              ⚠️ {doc.reconciliation_details.message}
                              {doc.reconciliation_details.ocr_invoice_number && <span> - OCR Invoice: <b>{doc.reconciliation_details.ocr_invoice_number}</b></span>}
                              {doc.reconciliation_details.ocr_amount && <span> - OCR Amount: <b>{doc.reconciliation_details.ocr_amount}</b></span>}
                              {doc.reconciliation_details.api_amount && <span> - API Amount: <b>{doc.reconciliation_details.api_amount}</b></span>}
                          </div>
                      )}
                    </div>
                  )})}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Document Details Modal */}
      {selectedDocument && (
          <div style={{
              position: 'fixed',
              top: 0, left: 0, right: 0, bottom: 0,
              backgroundColor: 'rgba(0, 0, 0, 0.5)',
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              zIndex: 10000
          }} onClick={closeDocumentModal}>
              <div
                  style={{
                      backgroundColor: 'var(--card-background)',
                      padding: '2rem',
                      borderRadius: '8px',
                      width: '80%',
                      maxWidth: '900px',
                      maxHeight: '90vh',
                      overflowY: 'auto',
                      boxShadow: '0 10px 25px rgba(0,0,0,0.2)',
                      color: 'var(--text-primary)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '1rem'
                  }}
                  onClick={(e) => e.stopPropagation()} // Prevent clicking inside modal from closing it
              >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid var(--card-border)', paddingBottom: '1rem' }}>
                      <h2 style={{ margin: 0 }}>Document Details: {selectedDocument.original_filename}</h2>
                      <button
                          onClick={closeDocumentModal}
                          style={{
                              background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer', color: 'var(--text-secondary)'
                          }}
                      >
                          &times;
                      </button>
                  </div>

                  <div style={{ display: 'flex', gap: '2rem', marginTop: '1rem' }}>
                      {/* Left Column: Parsed Data & API Match */}
                      <div style={{ flex: 1, minWidth: '400px' }}>
                          <div style={{ marginBottom: '1.5rem' }}>
                              <h3 style={{ fontSize: '1.1rem', marginBottom: '0.5rem', color: 'var(--primary-accent)' }}>Extracted Key Fields</h3>
                              <div style={{ backgroundColor: 'var(--background-secondary)', padding: '1rem', borderRadius: '6px', border: '1px solid var(--card-border)' }}>
                                  {selectedDocument.parsed_data ? (
                                      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                          <tbody>
                                              {Object.entries(selectedDocument.parsed_data).map(([key, value]) => {
                                                  // Skip rendering tables here, handle them below
                                                  if (key === 'tables') return null;
                                                  return (
                                                  <tr key={key} style={{ borderBottom: '1px solid var(--card-border)' }}>
                                                      <td style={{ padding: '8px 4px', fontWeight: 'bold', color: 'var(--text-secondary)', textTransform: 'capitalize' }}>{key.replace('_', ' ')}</td>
                                                      <td style={{ padding: '8px 4px' }}>{value !== null ? value.toString() : 'N/A'}</td>
                                                  </tr>
                                              )})}
                                          </tbody>
                                      </table>
                                  ) : (
                                      <p style={{ color: 'var(--text-secondary)', margin: 0 }}>No key fields extracted.</p>
                                  )}
                              </div>
                          </div>

                          <div style={{ marginBottom: '1.5rem' }}>
                              <h3 style={{ fontSize: '1.1rem', marginBottom: '0.5rem', color: 'var(--primary-accent)' }}>Reconciliation Status</h3>
                              <div style={{
                                  backgroundColor: getStatusColor(selectedDocument.reconciliation_status).bg,
                                  padding: '1rem',
                                  borderRadius: '6px',
                                  border: `1px solid ${getStatusColor(selectedDocument.reconciliation_status).text}`
                              }}>
                                  <strong style={{ color: getStatusColor(selectedDocument.reconciliation_status).text, display: 'block', marginBottom: '4px' }}>
                                      {formatStatus(selectedDocument.reconciliation_status)}
                                  </strong>
                                  {selectedDocument.reconciliation_details && (
                                      <pre style={{ fontSize: '0.85rem', whiteSpace: 'pre-wrap', wordWrap: 'break-word', color: 'var(--text-primary)', margin: 0 }}>
                                          {JSON.stringify(selectedDocument.reconciliation_details, null, 2)}
                                      </pre>
                                  )}
                              </div>
                          </div>
                      </div>

                      {/* Right Column: Full Text or matched API data */}
                      <div style={{ flex: 1 }}>
                         {selectedDocument.matched_bill_data && (
                              <div style={{ marginBottom: '1.5rem' }}>
                                  <h3 style={{ fontSize: '1.1rem', marginBottom: '0.5rem', color: 'var(--success)' }}>Matched System Bill Data</h3>
                                  <div style={{ backgroundColor: 'var(--background-secondary)', padding: '1rem', borderRadius: '6px', border: '1px solid var(--card-border)' }}>
                                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                                          <tbody>
                                              <tr><td style={{ padding: '4px', fontWeight: 'bold' }}>Invoice No:</td><td style={{ padding: '4px' }}>{selectedDocument.matched_bill_data.invoiceNo}</td></tr>
                                              <tr><td style={{ padding: '4px', fontWeight: 'bold' }}>Party Name:</td><td style={{ padding: '4px' }}>{selectedDocument.matched_bill_data.partyName}</td></tr>
                                              <tr><td style={{ padding: '4px', fontWeight: 'bold' }}>Payable:</td><td style={{ padding: '4px', color: 'var(--primary-accent)', fontWeight: 'bold' }}>{selectedDocument.matched_bill_data.payable}</td></tr>
                                              <tr><td style={{ padding: '4px', fontWeight: 'bold' }}>Goods Value:</td><td style={{ padding: '4px' }}>{selectedDocument.matched_bill_data.goodsValue}</td></tr>
                                              <tr><td style={{ padding: '4px', fontWeight: 'bold' }}>Tax Amount:</td><td style={{ padding: '4px' }}>{selectedDocument.matched_bill_data.taxAmount}</td></tr>
                                          </tbody>
                                      </table>
                                  </div>
                              </div>
                          )}

                          <div>
                              <h3 style={{ fontSize: '1.1rem', marginBottom: '0.5rem', color: 'var(--primary-accent)' }}>Raw Extracted Text</h3>
                              <div style={{
                                  backgroundColor: 'var(--background-secondary)',
                                  padding: '1rem',
                                  borderRadius: '6px',
                                  border: '1px solid var(--card-border)',
                                  maxHeight: '300px',
                                  overflowY: 'auto',
                                  fontSize: '0.85rem',
                                  fontFamily: 'monospace',
                                  whiteSpace: 'pre-wrap',
                                  color: 'var(--text-secondary)'
                              }}>
                                  {selectedDocument.extracted_text || 'No text extracted.'}
                              </div>
                          </div>
                      </div>
                  </div>

                  {/* Bottom Row: Extracted Tables */}
                  {selectedDocument.parsed_data && selectedDocument.parsed_data.tables && selectedDocument.parsed_data.tables.length > 0 && (
                      <div style={{ marginTop: '1.5rem', borderTop: '1px solid var(--card-border)', paddingTop: '1rem' }}>
                          <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--primary-accent)' }}>Extracted Tables</h3>

                          {selectedDocument.parsed_data.tables.map((table, idx) => {
                              // Reconstruct the table grid from cells
                              const grid = Array(table.row_count).fill(null).map(() => Array(table.column_count).fill(""));
                              table.cells.forEach(cell => {
                                  if (cell.row_index < table.row_count && cell.column_index < table.column_count) {
                                      grid[cell.row_index][cell.column_index] = cell.content;
                                  }
                              });

                              return (
                                  <div key={idx} style={{ marginBottom: '2rem', overflowX: 'auto' }}>
                                      <h4 style={{ fontSize: '0.9rem', marginBottom: '0.5rem', color: 'var(--text-secondary)' }}>Table {idx + 1}</h4>
                                      <table style={{ width: '100%', borderCollapse: 'collapse', border: '1px solid var(--card-border)' }}>
                                          <tbody>
                                              {grid.map((row, rowIndex) => (
                                                  <tr key={rowIndex}>
                                                      {row.map((cellContent, colIndex) => (
                                                          <td
                                                              key={colIndex}
                                                              style={{
                                                                  border: '1px solid var(--card-border)',
                                                                  padding: '8px',
                                                                  fontSize: '0.85rem',
                                                                  backgroundColor: rowIndex === 0 ? 'var(--background-secondary)' : 'transparent',
                                                                  fontWeight: rowIndex === 0 ? 'bold' : 'normal'
                                                              }}
                                                          >
                                                              {cellContent}
                                                          </td>
                                                      ))}
                                                  </tr>
                                              ))}
                                          </tbody>
                                      </table>
                                  </div>
                              );
                          })}
                      </div>
                  )}

              </div>
          </div>
      )}

    </div>
  );
};

export default Dashboard;