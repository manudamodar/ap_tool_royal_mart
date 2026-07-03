import React, { useRef, useState, useEffect } from 'react';

const DOCUMENT_DETAIL_FIELDS = [
  { key: 'date', label: 'Date' },
  { key: 'vendor_name', label: 'Vendor Name' },
  { key: 'vendor_bank', label: 'Vendor Bank' },
  { key: 'ifsc_code', label: 'IFSC Code' },
  { key: 'hsn_or_sac', label: 'HSN or SAC' },
  { key: 'vendor_gst_number', label: 'GST Number of Vendor' },
  { key: 'customer_gst_number', label: 'GST Number of Customer' },
  { key: 'total_amount', label: 'Total Amount' },
  { key: 'invoice_number', label: 'Invoice Number' },
];

const Dashboard = ({ user }) => {
  const [role, setRole] = useState(user.role);
  const fileInputRef = useRef(null);
  const dueReportInputRef = useRef(null);

  // State for tracking upload progress
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isDueReportUploading, setIsDueReportUploading] = useState(false);
  const [dueReport, setDueReport] = useState(null);

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
  const [, setIsFetchingDocument] = useState(false);

  // State for Editing Document
  const [isEditingDoc, setIsEditingDoc] = useState(false);
  const [editDocData, setEditDocData] = useState({});
  const [isSavingDoc, setIsSavingDoc] = useState(false);

  const [notification, setNotification] = useState(null); // { message, type }

  const scanningToastShownRef = useRef(null);

  useEffect(() => {
    fetchRecentBatches(currentPage);
  }, [role, currentPage]);

  useEffect(() => {
    fetchCurrentDueReport();
  }, []);

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

  const getCashDiscountDisplay = (cashDiscountData) => {
    if (!cashDiscountData) {
      return { percentage: 'Not Available', amountAfterDiscount: 'Not Available' };
    }

    if (cashDiscountData.match_found === false) {
      return { percentage: '0', amountAfterDiscount: 'Not Available' };
    }

    return {
      percentage: cashDiscountData.cash_discount_percentage != null ? cashDiscountData.cash_discount_percentage : '0',
      amountAfterDiscount: cashDiscountData.amount_after_discount != null ? cashDiscountData.amount_after_discount : 'Not Available',
    };
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

  const fetchCurrentDueReport = async () => {
    try {
      const response = await fetch('/api/due-report/current/');
      const data = await response.json();
      if (response.ok) {
        setDueReport(data.due_report || null);
      }
    } catch (error) {
      console.error("Error fetching current due report:", error);
    }
  };

  const handlePageChange = (newPage) => {
      if (newPage >= 1 && newPage <= totalPages) {
          setCurrentPage(newPage);
      }
  };

  const handleAction = (actionName) => {
    if (actionName === "Upload Due Report") {
      dueReportInputRef.current.click();
    } else if (actionName === "Upload Scanned Copy") {
      if (!dueReport) {
        showNotification("Upload the due report Excel file first.", "warning");
        return;
      }
      fileInputRef.current.click();
    } else {
      showNotification(`Action Triggered: ${actionName}`, "info");
    }
  };

  const onDueReportSelected = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    executeDueReportUpload(file);
  };

  const executeDueReportUpload = async (file) => {
    setIsDueReportUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/api/due-report/upload/', {
        method: 'POST',
        body: formData
      });
      const data = await response.json();

      if (response.ok) {
        setDueReport(data.due_report);
        showNotification(`Due report uploaded: ${data.due_report.row_count} bills loaded.`, "success");
      } else {
        showNotification(data.error || "Due report upload failed.", "error");
      }
    } catch (error) {
      console.error("Error uploading due report:", error);
      showNotification("An error occurred during due report upload.", "error");
    } finally {
      setIsDueReportUploading(false);
      if (dueReportInputRef.current) {
        dueReportInputRef.current.value = null;
      }
    }
  };

  const onFilesSelected = (event) => {
    const files = event.target.files;
    if (!files || files.length === 0) return;
    executeFolderUpload(files);
  };

  const executeFolderUpload = async (files) => {
    if (!dueReport) {
      showNotification("Upload the due report Excel file first.", "warning");
      return;
    }

    setIsUploading(true);
    setUploadProgress(0);
    setBatchStatus(null);
    setBatchData(null);
    scanningToastShownRef.current = null; // Reset for new upload

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
        setUploadProgress(100);
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
    } finally {
        setIsUploading(false);
        if (fileInputRef.current) {
           fileInputRef.current.value = null;
        }
    }
  };

  // Polling logic for active batch
  useEffect(() => {
    let pollInterval;

    if (activeBatchId && (!batchStatus || (batchStatus !== 'INVOICES_SCANNED' && batchStatus !== 'FAILED' && batchStatus !== 'MANUAL_REVIEW' && batchStatus !== 'COMPLETED')) && !isUploading) {
      pollInterval = setInterval(async () => {
        try {
          const response = await fetch(`/api/ocr/status/${activeBatchId}/`);
          const data = await response.json();

          if (response.ok) {
            if (data.status === 'INVOICES_SCANNING_IN_PROCESS' && scanningToastShownRef.current !== activeBatchId) {
                showNotification("Invoices scanning in process...", "info");
                scanningToastShownRef.current = activeBatchId;
            }

            setBatchStatus(data.status);

            // This ensures the table also updates its progress bar dynamically
            setRecentBatches(prevBatches =>
                prevBatches.map(b =>
                    b.batch_id === activeBatchId
                        ? { ...b, status: data.status, processed_files: data.processed_files, total_files: data.total_files }
                        : b
                )
            );

            if (data.total_files > 0) {
               setUploadProgress(Math.round((data.processed_files / data.total_files) * 100));
            }

            if (data.status === 'INVOICES_SCANNED' || data.status === 'FAILED' || data.status === 'MANUAL_REVIEW' || data.status === 'COMPLETED') {
              clearInterval(pollInterval);
              if (data.status === 'INVOICES_SCANNED' || data.status === 'COMPLETED') {
                 setBatchData(data.results);
                 showNotification("Batch processing complete! All documents verified.", "success");
              } else if (data.status === 'MANUAL_REVIEW') {
                 setBatchData(data.results);
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
  }, [activeBatchId, batchStatus, isUploading]);

  const handleBatchClick = async (batchId, status) => {
      setActiveBatchId(batchId);
      setBatchStatus(status);

      if (status === 'INVOICES_SCANNED' || status === 'MANUAL_REVIEW' || status === 'COMPLETED') {
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
              setEditDocData(data.parsed_data || {});
              setIsEditingDoc(false);
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
      setIsEditingDoc(false);
      setIsSavingDoc(false);
  };

  const handleEditDocChange = (e) => {
      const { name, value } = e.target;
      setEditDocData({
          ...editDocData,
          [name]: value
      });
  };

  const saveDocumentChanges = async () => {
      const changedFields = {};
      Object.keys(editDocData).forEach(key => {
          if (editDocData[key] !== selectedDocument.parsed_data[key]) {
              changedFields[key] = editDocData[key];
          }
      });

      if (Object.keys(changedFields).length === 0) {
          showNotification("No changes made.", "info");
          setIsEditingDoc(false);
          return;
      }

      setIsSavingDoc(true);

      try {
          const response = await fetch(`/api/ocr/document/${selectedDocument.document_id}/update/`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ updates: changedFields })
          });

          const data = await response.json();
          if (response.ok) {
              showNotification("Document updated and re-verified!", "success");
              setSelectedDocument(prev => ({ ...prev, ...data.document }));
              setEditDocData(data.document.parsed_data || {});
              setIsEditingDoc(false);

              if (activeBatchId) {
                  handleBatchClick(activeBatchId, data.batch_status);
                  fetchRecentBatches(currentPage);
              }
          } else {
              showNotification(data.error || "Failed to save changes", "error");
          }
      } catch (err) {
          console.error("Error saving document:", err);
          showNotification("Network error while saving.", "error");
      } finally {
          setIsSavingDoc(false);
      }
  };

  const getDisplayValue = (value) => {
      if (value === null || value === undefined) return null;
      const stringValue = value.toString().trim();
      return stringValue ? stringValue : null;
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
      if (isWarning) bgColor = '#faad14';

      return (
          <div style={{
              position: 'fixed', bottom: '24px', right: '24px', zIndex: 10001, // Increased z-index
              backgroundColor: bgColor,
              color: 'white', padding: '12px 20px', borderRadius: '8px',
              boxShadow: 'var(--shadow-lg)', fontWeight: '500',
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

  const FeatureCard = ({ iconSvg, title, description, onClick, isComingSoon, disabled = false, variant = 'default' }) => (
    <div
      onClick={!isComingSoon && !isUploading && !isDueReportUploading && !disabled ? onClick : undefined}
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
        cursor: (!isComingSoon && onClick && !isUploading && !isDueReportUploading && !disabled) ? 'pointer' : 'default',
        position: 'relative',
        opacity: (isComingSoon || disabled || (isUploading && title === "Upload Scanned Copy") || (isDueReportUploading && title === "Upload Due Report")) ? 0.7 : 1,
        borderColor: variant === 'danger' ? '#ff4d4f' : variant === 'success' ? '#52c41a' : 'var(--card-border)'
      }}
      onMouseEnter={(e) => {
         if(!isComingSoon && onClick && !isUploading && !isDueReportUploading && !disabled) {
             e.currentTarget.style.transform = 'translateY(-5px)';
             e.currentTarget.style.boxShadow = '0 8px 16px var(--shadow-color)';
         }
      }}
      onMouseLeave={(e) => {
         if(!isComingSoon && onClick && !isUploading && !isDueReportUploading && !disabled) {
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

      {isDueReportUploading && title === "Upload Due Report" && (
          <div style={{ marginTop: '15px', fontSize: '0.8rem', color: 'var(--primary-accent)', fontWeight: 'bold' }}>
              Uploading due report...
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

  const ReportIcon = (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
      <polyline points="14 2 14 8 20 8"></polyline>
      <line x1="8" y1="13" x2="16" y2="13"></line>
      <line x1="8" y1="17" x2="13" y2="17"></line>
      <polyline points="9 9 10 10 12 8"></polyline>
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
      // Better formatting for specific statuses
      if(statusStr === 'INVOICES_SCANNING_IN_PROCESS') return 'Scanning in Process';
      if(statusStr === 'INVOICES_SCANNED') return 'Verified';
      if(statusStr === 'MANUALLY_VERIFIED') return 'Manually Verified';
      if(statusStr === 'MANUAL_REVIEW') return 'Needs Review';

      // Fallback
      return statusStr.replace(/_/g, ' ');
  };

  const formatDate = (dateStr) => {
      if(!dateStr) return '';
      return new Date(dateStr).toLocaleString();
  };

  const getStatusColor = (status) => {
      switch (status) {
          case 'INVOICES_SCANNED':
          case 'COMPLETED':
          case 'VERIFIED':
          case 'MANUALLY_VERIFIED':
              return { bg: 'transparent', text: 'var(--success)' };
          case 'FAILED':
          case 'NO_MATCH':
              return { bg: 'transparent', text: 'var(--danger)' };
          case 'MANUAL_REVIEW':
              return { bg: 'transparent', text: '#d97706' }; // Standard warning text color
          case 'INVOICES_SCANNING_IN_PROCESS':
          case 'PROCESSING':
          case 'PENDING':
              return { bg: 'transparent', text: 'var(--primary-accent)' };
          default:
              return { bg: 'transparent', text: 'var(--text-secondary)' };
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
              iconSvg={ReportIcon}
              title="Upload Due Report"
              description={dueReport ? `${dueReport.filename} (${dueReport.row_count} bills)` : "Upload the due report Excel file before scanning bills."}
              onClick={() => handleAction("Upload Due Report")}
              variant={dueReport ? "success" : "default"}
            />
            <input
              type="file"
              ref={dueReportInputRef}
              style={{ display: 'none' }}
              accept=".xlsx"
              onChange={onDueReportSelected}
            />

            <FeatureCard
              iconSvg={UploadIcon}
              title="Upload Scanned Copy"
              description={dueReport ? "Select a folder containing scanned invoice copies (PDFs, Images)." : "Upload the due report first to enable bill scanning."}
              onClick={() => handleAction("Upload Scanned Copy")}
              disabled={!dueReport}
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
                                  <th style={{ padding: '12px 10px', color: 'var(--text-secondary)', fontWeight: '600' }}>Batch ID</th>
                                  <th style={{ padding: '12px 10px', color: 'var(--text-secondary)', fontWeight: '600' }}>Date & Time</th>
                                  <th style={{ padding: '12px 10px', color: 'var(--text-secondary)', fontWeight: '600' }}>Status</th>
                              </tr>
                          </thead>
                          <tbody style={{ opacity: isFetchingBatches ? 0.5 : 1, transition: 'opacity 0.2s' }}>
                              {recentBatches.map(batch => {
                                  const colors = getStatusColor(batch.status);
                                  const isProcessing = batch.status === 'INVOICES_SCANNING_IN_PROCESS' || batch.status === 'PENDING' || batch.status === 'PROCESSING';
                                  const pct = batch.total_files > 0 ? Math.round((batch.processed_files / batch.total_files) * 100) : 0;

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
                                      <td style={{ padding: '16px 10px', fontFamily: 'monospace', fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                                          {batch.batch_id}
                                      </td>
                                      <td style={{ padding: '16px 10px', fontSize: '0.9rem' }}>{formatDate(batch.created_at)}</td>

                                      <td style={{ padding: '16px 10px', fontSize: '0.85rem', fontWeight: '600', minWidth: '200px' }}>
                                          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                              <span style={{ color: colors.text }}>
                                                  {formatStatus(batch.status)} {isProcessing ? `(${batch.processed_files}/${batch.total_files})` : ''}
                                              </span>
                                              {/* In-row progress bar */}
                                              {isProcessing && (
                                                  <div style={{ width: '100%', height: '4px', backgroundColor: 'var(--card-border)', borderRadius: '2px', overflow: 'hidden' }}>
                                                      <div style={{ width: `${pct}%`, height: '100%', backgroundColor: colors.text, transition: 'width 0.3s ease' }}></div>
                                                  </div>
                                              )}
                                          </div>
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
            <h3 style={{ marginTop: 0, color: 'var(--text-primary)', fontSize: '1.2rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--card-border)', paddingBottom: '0.5rem' }}>
                Batch Details <span style={{ color: 'var(--text-secondary)', fontSize: '1rem', fontWeight: 'normal' }}>({activeBatchId})</span>
            </h3>

            {/* In-batch progress display logic */}
            {isUploading ? (
                <div style={{ width: '100%', height: '8px', backgroundColor: 'var(--background-secondary)', borderRadius: '4px', overflow: 'hidden', marginBottom: '1rem' }}>
                  <div style={{
                    height: '100%',
                    width: `${uploadProgress}%`,
                    backgroundColor: 'var(--primary-accent)',
                    transition: 'width 0.5s ease'
                  }} />
                </div>
            ) : (!batchData && (batchStatus === 'PENDING' || batchStatus === 'INVOICES_SCANNING_IN_PROCESS' || batchStatus === 'PROCESSING')) ? (
                <div style={{ textAlign: 'center', padding: '2rem' }}>
                    <div style={{ display: 'inline-block', width: '40px', height: '40px', border: '4px solid var(--background-secondary)', borderTopColor: 'var(--primary-accent)', borderRadius: '50%', animation: 'spin 1s linear infinite', marginBottom: '1rem' }}></div>
                    <style>{`@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }`}</style>
                    <h4 style={{ color: 'var(--primary-accent)', margin: 0 }}>Files are processing...</h4>
                    <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', marginTop: '0.5rem' }}>Please wait while the system extracts and reconciles the data.</p>
                </div>
            ) : batchData && (
              <div style={{ paddingTop: '0.5rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '1rem' }}>
                    <h4 style={{ color: batchStatus === 'MANUAL_REVIEW' ? '#d97706' : 'var(--success)', margin: 0, fontSize: '1.1rem' }}>
                        {batchStatus === 'MANUAL_REVIEW' ? 'Review Needed' : 'All Documents Verified'}
                    </h4>
                    <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>Total Documents: {batchData.length}</span>
                </div>

                <div style={{ maxHeight: '500px', overflowY: 'auto', paddingRight: '10px' }}>
                  {batchData.map((doc) => {
                     const docColors = getStatusColor(doc.reconciliation_status);
                     return (
                    <div
                      key={doc.id}
                      onClick={() => handleDocumentClick(doc.id)}
                      style={{
                          padding: '1.25rem',
                          border: '1px solid var(--card-border)',
                          borderRadius: '8px',
                          marginBottom: '1rem',
                          backgroundColor: 'var(--background-secondary)',
                          cursor: 'pointer',
                          transition: 'border-color 0.2s, transform 0.2s',
                          borderLeft: `4px solid ${docColors.text}`
                      }}
                      onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--text-secondary)'; e.currentTarget.style.transform = 'translateX(2px)'; }}
                      onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--card-border)'; e.currentTarget.style.transform = 'translateX(0)'; }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                          <strong style={{ fontSize: '1rem', color: 'var(--text-primary)' }}>{doc.filename}</strong>
                          <span style={{
                              fontSize: '0.75rem',
                              fontWeight: 'bold',
                              color: docColors.text,
                              textTransform: 'uppercase',
                              letterSpacing: '0.5px'
                          }}>
                              {formatStatus(doc.reconciliation_status)}
                          </span>
                      </div>

                      {doc.reconciliation_status !== 'VERIFIED' && doc.reconciliation_status !== 'MANUALLY_VERIFIED' && doc.reconciliation_details && doc.reconciliation_details.message && (
                          <div style={{ fontSize: '0.85rem', color: 'var(--danger)', marginTop: '12px', padding: '8px 12px', backgroundColor: 'var(--danger-bg)', borderRadius: '4px', borderLeft: '2px solid var(--danger)' }}>
                              <strong style={{ display: 'block', marginBottom: '4px' }}>⚠️ {doc.reconciliation_details.message}</strong>
                              <div style={{ display: 'flex', gap: '16px', color: 'var(--text-primary)' }}>
                                  {doc.reconciliation_details.ocr_invoice_number && <span>OCR Invoice: <b>{doc.reconciliation_details.ocr_invoice_number}</b></span>}
                                  {doc.reconciliation_details.ocr_amount && <span>OCR Amount: <b style={{color: 'var(--danger)'}}>{doc.reconciliation_details.ocr_amount}</b></span>}
                                  {doc.reconciliation_details.api_amount && <span>Due Report Amount: <b style={{color: 'var(--success)'}}>{doc.reconciliation_details.api_amount}</b></span>}
                                  {doc.reconciliation_details.cash_discount && (() => {
                                      const discountDisplay = getCashDiscountDisplay(doc.reconciliation_details.cash_discount);
                                      return (
                                          <>
                                              {doc.reconciliation_details.cash_discount.match_found === false && (
                                                  <span style={{ color: 'var(--warning)' }}>No cash discount rule found for the GST number.</span>
                                              )}
                                              <span>Cash Discount: <b style={{color: 'var(--primary-accent)'}}>{discountDisplay.percentage}%</b></span>
                                              <span>Amount After Discount: <b style={{color: 'var(--success)'}}>{discountDisplay.amountAfterDiscount}</b></span>
                                          </>
                                      );
                                  })()}
                              </div>
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

      {/* Document Details & Edit Modal */}
      {selectedDocument && (
          <div style={{
              position: 'fixed',
              top: 0, left: 0, right: 0, bottom: 0,
              backgroundColor: 'rgba(0, 0, 0, 0.6)',
              display: 'flex',
              justifyContent: 'center',
              alignItems: 'center',
              zIndex: 10000,
              backdropFilter: 'blur(4px)'
          }} onClick={closeDocumentModal}>
              <div
                  style={{
                      backgroundColor: 'var(--card-background)',
                      borderRadius: '12px',
                      width: '95%',
                      maxWidth: '1200px',
                      height: '90vh',
                      display: 'flex',
                      flexDirection: 'column',
                      boxShadow: '0 25px 50px -12px rgba(0,0,0,0.5)',
                      color: 'var(--text-primary)',
                      overflow: 'hidden'
                  }}
                  onClick={(e) => e.stopPropagation()}
              >
                  {/* Modal Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '1.5rem 2rem', borderBottom: '1px solid var(--card-border)', backgroundColor: 'var(--background-secondary)' }}>
                      <div>
                          <h2 style={{ margin: '0 0 0.5rem 0', fontSize: '1.4rem' }}>
                              Document Details: <span style={{ color: 'var(--text-secondary)', fontWeight: 'normal' }}>{selectedDocument.original_filename}</span>
                          </h2>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                              <span style={{
                                  fontSize: '0.8rem',
                                  fontWeight: 'bold',
                                  color: getStatusColor(selectedDocument.reconciliation_status).text,
                                  textTransform: 'uppercase'
                              }}>
                                  {formatStatus(selectedDocument.reconciliation_status)}
                              </span>
                              {selectedDocument.reconciliation_details?.message && (
                                  <span style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                                      | {selectedDocument.reconciliation_details.message}
                                  </span>
                              )}
                          </div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                          {selectedDocument.reconciliation_status !== 'VERIFIED' && selectedDocument.reconciliation_status !== 'MANUALLY_VERIFIED' && (
                              <button
                                  onClick={() => setIsEditingDoc(!isEditingDoc)}
                                  style={{ padding: '8px 16px', backgroundColor: isEditingDoc ? 'var(--background-secondary)' : 'var(--primary-accent)', color: isEditingDoc ? 'var(--text-primary)' : 'white', border: isEditingDoc ? '1px solid var(--card-border)' : 'none' }}
                              >
                                  {isEditingDoc ? 'Cancel Editing' : 'Manual Correction'}
                              </button>
                          )}
                          <button
                              onClick={closeDocumentModal}
                              style={{ background: 'none', border: 'none', fontSize: '1.5rem', cursor: 'pointer', color: 'var(--text-secondary)', padding: '0 8px' }}
                          >
                              &times;
                          </button>
                      </div>
                  </div>

                  {/* Modal Body - Scrollable */}
                  <div style={{ padding: '2rem', overflowY: 'auto', flex: 1 }}>
                      <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>

                          {/* Left Column: Parsed Data & Editing */}
                          <div style={{ flex: 1, minWidth: '350px' }}>
                              <div style={{ marginBottom: '2rem' }}>
                                  <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--text-primary)', borderBottom: '2px solid var(--primary-accent-light)', paddingBottom: '0.5rem' }}>Extracted Fields</h3>
                                  <div style={{ backgroundColor: 'var(--background-secondary)', borderRadius: '8px', border: '1px solid var(--card-border)', overflow: 'hidden' }}>

                                      {isEditingDoc ? (
                                          <div style={{ padding: '1.5rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                                  <label style={{ fontSize: '0.9rem', fontWeight: '600', color: 'var(--text-secondary)' }}>Invoice Number</label>
                                                  <input
                                                      type="text"
                                                      name="invoice_number"
                                                      value={editDocData.invoice_number || ''}
                                                      onChange={handleEditDocChange}
                                                      style={{ padding: '10px', borderRadius: '6px', border: '1px solid var(--primary-accent)', backgroundColor: 'var(--card-background)', color: 'var(--text-primary)', fontSize: '1rem' }}
                                                  />
                                              </div>
                                              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                                  <label style={{ fontSize: '0.9rem', fontWeight: '600', color: 'var(--text-secondary)' }}>Total Amount / Payable</label>
                                                  <input
                                                      type="number"
                                                      step="0.01"
                                                      name="total_amount"
                                                      value={editDocData.total_amount || ''}
                                                      onChange={handleEditDocChange}
                                                      style={{ padding: '10px', borderRadius: '6px', border: '1px solid var(--primary-accent)', backgroundColor: 'var(--card-background)', color: 'var(--text-primary)', fontSize: '1rem' }}
                                                  />
                                              </div>
                                              <button
                                                onClick={saveDocumentChanges}
                                                disabled={isSavingDoc}
                                                style={{ marginTop: '1rem', padding: '12px', backgroundColor: 'var(--success)', fontSize: '1rem', opacity: isSavingDoc ? 0.7 : 1 }}
                                              >
                                                  {isSavingDoc ? 'Saving...' : 'Save Corrections & Re-verify'}
                                              </button>
                                          </div>
                                      ) : selectedDocument.parsed_data ? (
                                          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                              <tbody>
                                                  {DOCUMENT_DETAIL_FIELDS.map(({ key, label }) => {
                                                      const value = getDisplayValue(selectedDocument.parsed_data[key]);
                                                      const isHighlighted = key === 'invoice_number' || key === 'total_amount';
                                                      return (
                                                      <tr key={key} style={{ borderBottom: '1px solid var(--card-border)' }}>
                                                          <td style={{ padding: '12px 16px', fontWeight: '600', color: 'var(--text-secondary)', width: '40%', backgroundColor: 'rgba(0,0,0,0.02)' }}>{label}</td>
                                                          <td style={{ padding: '12px 16px', fontWeight: isHighlighted ? 'bold' : 'normal', color: isHighlighted ? 'var(--primary-accent)' : 'var(--text-primary)', fontSize: isHighlighted ? '1.05rem' : '0.95rem' }}>
                                                              {value || <span style={{color: 'var(--text-secondary)', fontStyle: 'italic'}}>Not Available</span>}
                                                          </td>
                                                      </tr>
                                                  )})}
                                              </tbody>
                                          </table>
                                      ) : (
                                          <p style={{ padding: '1rem', color: 'var(--text-secondary)', margin: 0 }}>No key fields extracted.</p>
                                      )}
                                  </div>
                              </div>

                              {/* Matched due report data directly below parsed data for easy comparison */}
                              <div style={{ marginBottom: '2rem' }}>
                                  <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--text-primary)', borderBottom: '2px solid var(--success-bg)', paddingBottom: '0.5rem' }}>Matched Due Report Data</h3>
                                  {selectedDocument.matched_bill_data ? (
                                      <div style={{ backgroundColor: 'var(--background-secondary)', borderRadius: '8px', border: '1px solid var(--card-border)', overflow: 'hidden' }}>
                                          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.95rem' }}>
                                              <tbody>
                                                  <tr style={{ borderBottom: '1px solid var(--card-border)' }}><td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontWeight: '600', width: '40%', backgroundColor: 'rgba(0,0,0,0.02)' }}>Invoice No:</td><td style={{ padding: '12px 16px', fontWeight: 'bold' }}>{selectedDocument.matched_bill_data.invoiceNo}</td></tr>
                                                  <tr style={{ borderBottom: '1px solid var(--card-border)' }}><td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontWeight: '600', backgroundColor: 'rgba(0,0,0,0.02)' }}>Party Name:</td><td style={{ padding: '12px 16px' }}>{selectedDocument.matched_bill_data.partyName}</td></tr>
                                                  <tr style={{ borderBottom: '1px solid var(--card-border)' }}><td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontWeight: '600', backgroundColor: 'rgba(0,0,0,0.02)' }}>Payable:</td><td style={{ padding: '12px 16px', color: 'var(--text-primary)', fontWeight: 'bold', fontSize: '1.05rem' }}>{selectedDocument.matched_bill_data.payable}</td></tr>
                                                  <tr style={{ borderBottom: '1px solid var(--card-border)' }}><td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontWeight: '600', backgroundColor: 'rgba(0,0,0,0.02)' }}>Goods Value:</td><td style={{ padding: '12px 16px' }}>{selectedDocument.matched_bill_data.goodsValue}</td></tr>
                                                  <tr style={{ borderBottom: '1px solid var(--card-border)' }}><td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontWeight: '600', backgroundColor: 'rgba(0,0,0,0.02)' }}>Tax Amount:</td><td style={{ padding: '12px 16px' }}>{selectedDocument.matched_bill_data.taxAmount}</td></tr>
                                                  {selectedDocument.reconciliation_details?.cash_discount && (() => {
                                                      const discountDisplay = getCashDiscountDisplay(selectedDocument.reconciliation_details.cash_discount);
                                                      return (
                                                          <>
                                                              <tr style={{ borderBottom: '1px solid var(--card-border)' }}>
                                                                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontWeight: '600', backgroundColor: 'rgba(0,0,0,0.02)' }}>GST Used:</td>
                                                                  <td style={{ padding: '12px 16px', fontWeight: 'bold' }}>{selectedDocument.reconciliation_details.cash_discount.supplier_gst_number ?? 'Not Available'}</td>
                                                              </tr>
                                                              {selectedDocument.reconciliation_details.cash_discount.match_found === false && (
                                                                  <tr style={{ borderBottom: '1px solid var(--card-border)' }}>
                                                                      <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontWeight: '600', backgroundColor: 'rgba(0,0,0,0.02)' }}>Cash Discount:</td>
                                                                      <td style={{ padding: '12px 16px', color: 'var(--warning)', fontWeight: 'bold' }}>No matching GST rule found</td>
                                                                  </tr>
                                                              )}
                                                              <tr style={{ borderBottom: '1px solid var(--card-border)' }}>
                                                                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontWeight: '600', backgroundColor: 'rgba(0,0,0,0.02)' }}>Cash Discount %:</td>
                                                                  <td style={{ padding: '12px 16px', color: 'var(--primary-accent)', fontWeight: 'bold' }}>{discountDisplay.percentage}</td>
                                                              </tr>
                                                              <tr>
                                                                  <td style={{ padding: '12px 16px', color: 'var(--text-secondary)', fontWeight: '600', backgroundColor: 'rgba(0,0,0,0.02)' }}>Amount After Discount:</td>
                                                                  <td style={{ padding: '12px 16px', color: 'var(--success)', fontWeight: 'bold', fontSize: '1.05rem' }}>{discountDisplay.amountAfterDiscount}</td>
                                                              </tr>
                                                          </>
                                                      );
                                                  })()}
                                              </tbody>
                                          </table>
                                      </div>
                                  ) : (
                                      <div style={{ backgroundColor: 'var(--background-secondary)', padding: '1.5rem', borderRadius: '8px', border: '1px dashed var(--card-border)' }}>
                                          <p style={{ margin: 0, color: 'var(--text-secondary)', fontWeight: '500', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                                              No matching bill found in the due report for this invoice number.
                                          </p>
                                      </div>
                                  )}
                              </div>
                          </div>

                          {/* Right Column: Full Text & Audit Trail */}
                          <div style={{ flex: 1, minWidth: '350px', display: 'flex', flexDirection: 'column', gap: '2rem' }}>

                              {/* Audit Trail Section */}
                              <div style={{ display: 'flex', flexDirection: 'column', flex: 1 }}>
                                  <h3 style={{ fontSize: '1.1rem', marginBottom: '1rem', color: 'var(--text-primary)', borderBottom: '2px solid var(--card-border)', paddingBottom: '0.5rem' }}>Audit Log</h3>
                                  <div style={{
                                      display: 'flex',
                                      flexDirection: 'column',
                                      gap: '12px',
                                      maxHeight: '350px', // Set a maximum height for the audit log area
                                      overflowY: 'auto',  // Make it scrollable
                                      paddingRight: '10px' // Add a bit of padding for the scrollbar
                                  }}>
                                      {/* Manual Corrections - Rendered IN REVERSE ORDER (latest first) */}
                                      {selectedDocument.audit_trail && [...selectedDocument.audit_trail].reverse().map((log, idx) => (
                                          <div key={idx} style={{ padding: '12px 16px', backgroundColor: 'var(--card-background)', borderLeft: '4px solid var(--primary-accent)', borderRadius: '6px', fontSize: '0.9rem', border: '1px solid var(--card-border)', borderLeftWidth: '4px' }}>
                                              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                                                  <span>{formatDate(log.timestamp)}</span>
                                                  <span>{log.user_name}</span>
                                              </div>
                                              <strong style={{ color: 'var(--primary-accent)' }}>{log.action}</strong>

                                              {/* Formatted details showing old -> new values */}
                                              <div style={{ marginTop: '8px', backgroundColor: 'var(--background-secondary)', padding: '8px', borderRadius: '4px' }}>
                                                  {log.changes && Object.entries(log.changes).map(([field, change]) => (
                                                      <div key={field} style={{ marginBottom: '4px', fontSize: '0.85rem', display: 'flex', alignItems: 'center' }}>
                                                          <span style={{ fontWeight: '600', textTransform: 'capitalize', color: 'var(--text-primary)', width: '120px' }}>{field.replace('_', ' ')}: </span>
                                                          <span style={{ color: 'var(--text-secondary)', textDecoration: 'line-through' }}>{change.old || 'None'}</span>
                                                          <span style={{ margin: '0 8px', color: 'var(--text-secondary)' }}>➔</span>
                                                          <span style={{ color: 'var(--success)', fontWeight: 'bold' }}>{change.new || 'None'}</span>
                                                      </div>
                                                  ))}
                                              </div>
                                          </div>
                                      ))}

                                      {/* System Creation Log (Always at the bottom / oldest) */}
                                      <div style={{ padding: '12px 16px', backgroundColor: 'var(--background-secondary)', borderLeft: '4px solid var(--text-secondary)', borderRadius: '6px', fontSize: '0.9rem' }}>
                                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', color: 'var(--text-secondary)', fontSize: '0.8rem' }}>
                                              <span>{formatDate(selectedDocument.processed_at)}</span>
                                              <span>System Process</span>
                                          </div>
                                          <strong style={{ color: 'var(--text-primary)' }}>Document Processed</strong>
                                          <p style={{ margin: '4px 0 0 0', color: 'var(--text-secondary)' }}>Initial OCR extraction and reconciliation attempted.</p>
                                      </div>
                                  </div>
                              </div>
                          </div>
                      </div>

                      {/* Bottom Row: Extracted Tables */}
                      {selectedDocument.parsed_data && selectedDocument.parsed_data.tables && selectedDocument.parsed_data.tables.length > 0 && (
                          <div style={{ marginTop: '3rem', borderTop: '1px solid var(--card-border)', paddingTop: '2rem' }}>
                              <h3 style={{ fontSize: '1.2rem', marginBottom: '1.5rem', color: 'var(--text-primary)' }}>Extracted Line Items (Tables)</h3>

                              {selectedDocument.parsed_data.tables.map((table, idx) => {
                                  const grid = Array(table.row_count).fill(null).map(() => Array(table.column_count).fill(""));
                                  table.cells.forEach(cell => {
                                      if (cell.row_index < table.row_count && cell.column_index < table.column_count) {
                                          grid[cell.row_index][cell.column_index] = cell.content;
                                      }
                                  });

                                  return (
                                      <div key={idx} style={{ marginBottom: '2.5rem', overflowX: 'auto', backgroundColor: 'var(--background-secondary)', padding: '1rem', borderRadius: '8px', border: '1px solid var(--card-border)' }}>
                                          <h4 style={{ fontSize: '0.95rem', marginBottom: '1rem', color: 'var(--text-secondary)' }}>Table {idx + 1}</h4>
                                          <table style={{ width: '100%', borderCollapse: 'collapse', backgroundColor: 'var(--card-background)' }}>
                                              <tbody>
                                                  {grid.map((row, rowIndex) => (
                                                      <tr key={rowIndex}>
                                                          {row.map((cellContent, colIndex) => (
                                                              <td
                                                                  key={colIndex}
                                                                  style={{
                                                                      border: '1px solid var(--card-border)',
                                                                      padding: '12px',
                                                                      fontSize: '0.85rem',
                                                                      backgroundColor: rowIndex === 0 ? 'var(--background-secondary)' : 'transparent',
                                                                      fontWeight: rowIndex === 0 ? 'bold' : 'normal',
                                                                      color: rowIndex === 0 ? 'var(--text-secondary)' : 'var(--text-primary)'
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
          </div>
      )}

    </div>
  );
};

export default Dashboard;
