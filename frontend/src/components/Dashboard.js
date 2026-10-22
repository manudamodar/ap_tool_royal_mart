import React, { useRef, useState, useEffect } from 'react';

const DOCUMENT_DETAIL_FIELDS = [
  { key: 'invoice_number', label: 'Invoice Number' },
  { key: 'date', label: 'Invoice Date', inputType: 'date' },
  { key: 'vendor_name', label: 'Vendor Name' },
  { key: 'vendor_gst_number', label: 'GST Number of Vendor' },
  { key: 'customer_gst_number', label: 'GST Number of Customer' },
  { key: 'total_amount', label: 'Total Amount / Payable', inputType: 'number', step: '0.01' },
  { key: 'goods_value', label: 'Goods Value', inputType: 'number', step: '0.01' },
  { key: 'tax_amount', label: 'Tax Amount', inputType: 'number', step: '0.01' },
  { key: 'hsn_or_sac', label: 'HSN or SAC' },
  { key: 'vendor_bank', label: 'Vendor Bank' },
  { key: 'bank_name', label: 'Bank Name' },
  { key: 'account_holder_name', label: 'Account Holder Name' },
  { key: 'account_number', label: 'Account Number' },
  { key: 'ifsc_code', label: 'IFSC Code' },
  { key: 'branch_name', label: 'Bank Branch' },
  { key: 'micr_code', label: 'MICR Code' },
  { key: 'swift_code', label: 'SWIFT Code' },
];

const VERIFIED_RECO_STATUSES = ['VERIFIED', 'MANUALLY_VERIFIED'];

const COMMON_INVOICE_FIELDS = [
  ['Invoice Number', 'invoice_no', 'invoice_number', 'invoice_number_matches'],
  ['Invoice Date', 'invoice_date', 'date', null],
  ['Vendor Name', 'supplier_name', 'vendor_name', null],
  ['Vendor GST', 'gst_number', 'vendor_gst_number', 'vendor_gst_matches'],
  ['Payable', 'payable', 'total_amount', 'payable_amount_matches'],
  ['Goods Value', 'goods_value', 'goods_value', 'goods_value_matches'],
  ['Tax Amount', 'tax_amount', 'tax_amount', 'tax_amount_matches'],
  ['Tax Type', 'tax_type', 'expected_tax_type', 'tax_type_matches'],
];

const DUE_REPORT_ONLY_FIELDS = [
  ['party_code', 'Party Code'], ['location_name', 'Royal Mart Store'],
  ['branch_code', 'Branch Code'], ['tran_year', 'Financial Year'], ['voucher_no', 'Voucher Number'],
  ['voucher_type', 'Voucher Type'], ['ref_no', 'Reference Number'], ['bill_unique_id', 'Bill Unique ID'],
  ['bill_voucher_date', 'Bill Voucher Date'], ['bill_date', 'Bill Date'], ['bill_amount', 'Voucher Amount'],
  ['tax_code', 'Report Tax Code'], ['tds_amount', 'TDS Amount'],
  ['tds_section', 'TDS Section'], ['disc_amount', 'Discount Amount'], ['other_charges', 'Other Charges'],
  ['amount_adjusted', 'Amount Adjusted'], ['balance_amount', 'Balance Amount'], ['pending_adj_amt', 'Pending Adjustment'],
  ['net_balance', 'Net Balance'], ['no_of_days', 'Due Days'], ['due_date', 'Due Date'],
  ['over_due_days', 'Overdue Days'], ['prior_date', 'Prior Date'], ['group_name', 'Group Name'],
  ['expense_ledger', 'Expense Ledger'], ['msme_type', 'MSME Type'], ['pay_mode', 'Payment Mode'],
  ['payment_status', 'Payment Status'], ['party_contact', 'Party Contact'], ['email_id', 'Email'],
  ['transaction_link', 'Transaction Link'],
];

const SCANNED_INVOICE_ONLY_FIELDS = [
  ['scanned_filename', 'Scanned File'], ['customer_gst_number', 'Customer/Store GST'],
  ['hsn_or_sac', 'HSN or SAC'], ['vendor_bank', 'Vendor Bank'], ['bank_name', 'Bank Name'],
  ['account_holder_name', 'Account Holder'], ['account_number', 'Account Number'],
  ['ifsc_code', 'IFSC Code'], ['branch_name', 'Bank Branch'], ['micr_code', 'MICR Code'],
  ['swift_code', 'SWIFT Code'],
];

const normalizeBooleanFlag = (value) => {
  return (value === true) || (String(value).toLowerCase() === 'true') || (value === 1) || (value === '1');
};

const normalizeInvoiceRecoStatus = (value) => {
  const normalized = (value || 'UNVERIFIED').toString().trim().toUpperCase();
  return ['VERIFIED', 'MANUALLY_VERIFIED', 'MANUAL_REVIEW', 'NO_MATCH', 'UNVERIFIED', 'PENDING'].includes(normalized) ? normalized : 'UNVERIFIED';
};

const getFormattedDownloadUrl = (url, format) => {
  if (!url) return '';
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}format=${format}`;
};

const Dashboard = ({ user }) => {
  const [role, setRole] = useState(user.role);
  const fileInputRef = useRef(null);
  const bankFileInputRef = useRef(null);

  // State for tracking upload progress
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isDueReportFetching, setIsDueReportFetching] = useState(false);
  const [invoiceDataReady, setInvoiceDataReady] = useState(false);
  const [isDueReportModalOpen, setIsDueReportModalOpen] = useState(false);
  const [dueReportRows, setDueReportRows] = useState([]);
  const [dueReportPagination, setDueReportPagination] = useState({ current_page: 1, total_pages: 1, total_items: 0 });
  const [dueReportStores, setDueReportStores] = useState([]);
  const [dueReportSearch, setDueReportSearch] = useState('');
  const [dueReportStoreFilter, setDueReportStoreFilter] = useState('');
  const [dueReportStatusFilter, setDueReportStatusFilter] = useState('');
  const [selectedDueReportRow, setSelectedDueReportRow] = useState(null);

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

  const [isPaymentFileModalOpen, setIsPaymentFileModalOpen] = useState(false);
  const [invoiceRows, setInvoiceRows] = useState([]);
  const [selectedInvoiceIds, setSelectedInvoiceIds] = useState([]);
  const [paymentType, setPaymentType] = useState('ICICI');
  const [paymentFileFormat, setPaymentFileFormat] = useState('xlsx');
  const [isFetchingInvoiceRows, setIsFetchingInvoiceRows] = useState(false);
  const [isGeneratingPaymentFile, setIsGeneratingPaymentFile] = useState(false);
  const [paymentFileResult, setPaymentFileResult] = useState(null);
  const [collapsedInvoiceSections, setCollapsedInvoiceSections] = useState({
    fresh: false,
    rejected: false,
    unverified: true,
    unscanned: true,
    approved: true,
  });

  const [paymentFiles, setPaymentFiles] = useState([]);
  const [paymentFilesStatusFilter, setPaymentFilesStatusFilter] = useState('PENDING');
  const [paymentFilesAccountantFilter, setPaymentFilesAccountantFilter] = useState('ALL');
  const [isPaymentFilesModalOpen, setIsPaymentFilesModalOpen] = useState(false);
  const [isFetchingPaymentFiles, setIsFetchingPaymentFiles] = useState(false);
  const [selectedPaymentFile, setSelectedPaymentFile] = useState(null);
  const [isFetchingSelectedPaymentFile, setIsFetchingSelectedPaymentFile] = useState(false);
  const [reviewEdits, setReviewEdits] = useState({});
  const [reviewRejectedIds, setReviewRejectedIds] = useState([]);
  const [reviewReason, setReviewReason] = useState('');
  const [isSubmittingReview, setIsSubmittingReview] = useState(false);
  const [isRegeneratingPaymentFile, setIsRegeneratingPaymentFile] = useState(false);
  const [regenerationInvoiceIds, setRegenerationInvoiceIds] = useState([]);
  const [apRejectedComments, setApRejectedComments] = useState({});
  const [isUploadingBankFile, setIsUploadingBankFile] = useState(false);

  // State for full-screen payment file preview modal
  const [isPaymentFilePreviewModalOpen, setIsPaymentFilePreviewModalOpen] = useState(false);
  const [previewPaymentFile, setPreviewPaymentFile] = useState(null);
  const [isFetchingPreviewPaymentFile, setIsFetchingPreviewPaymentFile] = useState(false);

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

  const fetchDueReport = async ({
    notify = true,
    page = 1,
    openTable = false,
    q = dueReportSearch,
    store = dueReportStoreFilter,
    status = dueReportStatusFilter,
  } = {}) => {
    setIsDueReportFetching(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: '100' });
      if (q.trim()) params.set('q', q.trim());
      if (store) params.set('store', store);
      if (status) params.set('status', status);
      const response = await fetch(`/api/rest/payable/getbills?${params.toString()}`);
      const data = await response.json();
      if (response.ok) {
        const rows = Array.isArray(data.data) ? data.data : [];
        const rowCount = data.pagination?.total_items ?? rows.length;
        setInvoiceDataReady(rowCount > 0);
        setDueReportRows(rows);
        setDueReportPagination(data.pagination || { current_page: 1, total_pages: 1, total_items: rowCount });
        setDueReportStores(data.filters?.stores || []);
        if (openTable) setIsDueReportModalOpen(true);
        if (notify) showNotification(`Due report loaded: ${rowCount} invoices found.`, 'success');
      } else if (notify) {
        showNotification(data.error || data.message || 'Unable to fetch due report.', 'error');
      }
    } catch (error) {
      console.error("Error fetching due report:", error);
      if (notify) showNotification('Unable to fetch due report.', 'error');
    } finally {
      setIsDueReportFetching(false);
    }
  };

  const handlePageChange = (newPage) => {
      if (newPage >= 1 && newPage <= totalPages) {
          setCurrentPage(newPage);
      }
  };

  const handleAction = (actionName) => {
    if (actionName === "Get Due Report") {
      setDueReportSearch('');
      setDueReportStoreFilter('');
      setDueReportStatusFilter('');
      fetchDueReport({ q: '', store: '', status: '' });
    } else if (actionName === "View Due Report") {
      fetchDueReport({ notify: false, page: 1, openTable: true });
    } else if (actionName === "Upload Scanned Copy") {
      if (!invoiceDataReady) {
        showNotification("Get the due report first.", "warning");
        return;
      }
      fileInputRef.current.click();
    } else if (actionName === "Generate Payment File") {
      if (!invoiceDataReady) {
        showNotification("Get the due report first.", "warning");
        return;
      }
      setIsPaymentFileModalOpen(true);
      fetchInvoiceRows();
    } else if (actionName === "View Payment Files") {
      setPaymentFilesStatusFilter('ALL');
      setPaymentFilesAccountantFilter('ALL');
      setIsPaymentFilesModalOpen(true);
      setSelectedPaymentFile(null);
      setReviewEdits({});
      setReviewRejectedIds([]);
      setReviewReason('');
      fetchPaymentFiles();
    } else if (actionName === "View Waiting Payment Files") {
      setPaymentFilesStatusFilter('PENDING');
      setPaymentFilesAccountantFilter('ALL');
      setIsPaymentFilesModalOpen(true);
      setSelectedPaymentFile(null);
      setReviewEdits({});
      setReviewRejectedIds([]);
      setReviewReason('');
      fetchPaymentFiles();
    } else if (actionName === "View Approved Payment Files") {
      setPaymentFilesStatusFilter('APPROVED');
      setPaymentFilesAccountantFilter('ALL');
      setIsPaymentFilesModalOpen(true);
      setSelectedPaymentFile(null);
      setReviewEdits({});
      setReviewRejectedIds([]);
      setReviewReason('');
      fetchPaymentFiles();
    } else {
      showNotification(`Action Triggered: ${actionName}`, "info");
    }
  };

  const fetchInvoiceRows = async () => {
    setIsFetchingInvoiceRows(true);
    try {
      const response = await fetch('/api/rest/payable/getbills?all=true');
      const data = await response.json();
      if (response.ok) {
        const rows = Array.isArray(data.data) ? data.data : [];
        // Normalize IDs to numbers and ensure boolean flags are proper booleans
        const normalized = rows.map(r => ({
          ...r,
          id: typeof r.id === 'string' ? Number(r.id) : r.id,
          is_payment_file_created: normalizeBooleanFlag(r.is_payment_file_created),
          is_available_for_payment: normalizeBooleanFlag(r.is_available_for_payment),
          payment_file_rejected: normalizeBooleanFlag(r.payment_file_rejected),
          manager_rejected: normalizeBooleanFlag(r.manager_rejected),
          invoice_scanned: normalizeBooleanFlag(r.invoice_scanned),
          invoice_reconciliation_status: normalizeInvoiceRecoStatus(r.invoice_reconciliation_status),
        }));
        setInvoiceRows(normalized);
        setSelectedInvoiceIds([]);
        setPaymentFileResult(null);
      } else {
        showNotification(data.error || 'Failed to load invoice rows.', 'error');
      }
    } catch (error) {
      console.error('Error loading invoice rows:', error);
      showNotification('Unable to load invoice rows.', 'error');
    } finally {
      setIsFetchingInvoiceRows(false);
    }
  };

  const fetchPaymentFiles = async () => {
    setIsFetchingPaymentFiles(true);
    try {
      const response = await fetch('/api/rest/central-payment');
      const data = await response.json();
      if (response.ok) {
        const files = Array.isArray(data.payment_files) ? data.payment_files : [];
        setPaymentFiles(files.map(file => ({
          ...file,
          created_by_id: file.created_by_id != null ? String(file.created_by_id) : null,
          payment_status: file.payment_status || 'PENDING',
        })));
      } else {
        showNotification(data.error || 'Unable to load payment files.', 'error');
      }
    } catch (error) {
      console.error('Error fetching payment files:', error);
      showNotification('Unable to load payment files.', 'error');
    } finally {
      setIsFetchingPaymentFiles(false);
    }
  };

  const fetchPaymentFileDetail = async (paymentFileId) => {
    setIsFetchingSelectedPaymentFile(true);
    try {
      const response = await fetch(`/api/rest/central-payment/${paymentFileId}/`);
      const data = await response.json();
      if (response.ok) {
        const paymentFile = data.payment_file || null;
        setSelectedPaymentFile(paymentFile);
        // In a rejected file, carry forward individually approved invoices by
        // default. Specifically rejected invoices stay optional and unchecked.
        setRegenerationInvoiceIds(
          paymentFile?.payment_status === 'REJECTED'
            ? (paymentFile.rows || []).filter((row) => !row.is_rejected).map((row) => row.id)
            : []
        );
        setReviewEdits({});
        setReviewRejectedIds([]);
        setApRejectedComments({});
        setReviewReason('');
      } else {
        showNotification(data.error || 'Unable to load payment file details.', 'error');
      }
    } catch (error) {
      console.error('Error fetching payment file detail:', error);
      showNotification('Unable to load payment file details.', 'error');
    } finally {
      setIsFetchingSelectedPaymentFile(false);
    }
  };

  const openPaymentFilePreview = async (paymentFileId) => {
    setIsFetchingPreviewPaymentFile(true);
    setIsPaymentFilePreviewModalOpen(true);
    try {
      const response = await fetch(`/api/rest/central-payment/${paymentFileId}/`);
      const data = await response.json();
      if (response.ok) {
        setPreviewPaymentFile(data.payment_file || null);
      } else {
        showNotification(data.error || 'Unable to load payment file preview.', 'error');
      }
    } catch (error) {
      console.error('Error fetching payment file preview:', error);
      showNotification('Unable to load payment file preview.', 'error');
    } finally {
      setIsFetchingPreviewPaymentFile(false);
    }
  };

  const closePaymentFilePreviewModal = () => {
    setIsPaymentFilePreviewModalOpen(false);
    setPreviewPaymentFile(null);
  };

  const accountantOptions = [
    { id: 'ALL', label: 'All accountants' },
    ...Array.from(
      paymentFiles.reduce((map, file) => {
        if (file.created_by_id) {
          map.set(file.created_by_id, file.created_by);
        }
        return map;
      }, new Map())
    ).map(([id, name]) => ({ id, label: name }))
  ];

  const filteredPaymentFiles = paymentFiles.filter((file) => {
    const matchesStatus = paymentFilesStatusFilter === 'ALL' || file.payment_status === paymentFilesStatusFilter;
    const matchesAccountant = paymentFilesAccountantFilter === 'ALL' || file.created_by_id === paymentFilesAccountantFilter;
    return matchesStatus && matchesAccountant;
  });

  const closePaymentFilesModal = () => {
    setIsPaymentFilesModalOpen(false);
    setPaymentFiles([]);
    setSelectedPaymentFile(null);
    setReviewEdits({});
    setReviewRejectedIds([]);
    setReviewReason('');
    setPaymentFilesStatusFilter('PENDING');
    setPaymentFilesAccountantFilter('ALL');
  };

  const toggleReviewReject = (rowId) => {
    setReviewRejectedIds((current) =>
      current.includes(rowId) ? current.filter((id) => id !== rowId) : [...current, rowId]
    );
  };

  const isInvoiceSelectableForPayment = (row) => {
    if (!row?.id) return false;
    const isRecoEligible = VERIFIED_RECO_STATUSES.includes(normalizeInvoiceRecoStatus(row.invoice_reconciliation_status));
    if (!row.invoice_scanned || !isRecoEligible) return false;
    return row.is_available_for_payment ?? (!row.is_payment_file_created || row.manager_rejected);
  };

  const toggleInvoiceSelection = (invoiceId) => {
    const id = typeof invoiceId === 'string' ? Number(invoiceId) : invoiceId;
    if (!id && id !== 0) return; // ignore rows without a valid numeric id
    setSelectedInvoiceIds((current) =>
      current.includes(id)
        ? current.filter((cid) => cid !== id)
        : [...current, id]
    );
  };

  const toggleSelectAll = () => {
    const selectable = invoiceRows.filter((row) => isInvoiceSelectableForPayment(row)).map((row) => (typeof row.id === 'string' ? Number(row.id) : row.id));
    const allSelected = selectable.length > 0 && selectable.every(id => selectedInvoiceIds.includes(id));
    if (allSelected) {
      setSelectedInvoiceIds([]);
    } else {
      setSelectedInvoiceIds(selectable);
    }
  };

  const generatePaymentFile = async () => {
    if (selectedInvoiceIds.length === 0) {
      showNotification('Select at least one invoice to generate a payment file.', 'warning');
      return;
    }

    setIsGeneratingPaymentFile(true);
    try {
      const response = await fetch('/api/rest/central-payment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invoice_ids: selectedInvoiceIds, payment_type: paymentType, file_format: paymentFileFormat }),
      });
      const data = await response.json();
      if (response.ok) {
        const processedInvoiceIds = Array.isArray(data.processed_invoice_ids)
          ? data.processed_invoice_ids
          : selectedInvoiceIds;
        const failedInvoices = Array.isArray(data.failed_invoices) ? data.failed_invoices : [];
        setPaymentFileResult(data.payment_file || null);
        showNotification(
          failedInvoices.length
            ? `Payment file generated for ${processedInvoiceIds.length} invoice(s); ${failedInvoices.length} invoice(s) failed TrueBooks processing.`
            : 'Payment file generated successfully.',
          failedInvoices.length ? 'warning' : 'success'
        );
        setInvoiceRows((currentRows) =>
          currentRows.map((row) =>
            processedInvoiceIds.includes(row.id)
              ? {
                  ...row,
                  is_payment_file_created: true,
                  manager_rejected: false,
                  invoice_scanned: true,
                  invoice_reconciliation_status: row.invoice_reconciliation_status || 'VERIFIED',
                }
              : row
          )
        );
        setSelectedInvoiceIds(failedInvoices.map((invoice) => invoice.id));
      } else {
        showNotification(data.error || 'Payment file creation failed.', 'error');
      }
    } catch (error) {
      console.error('Error generating payment file:', error);
      showNotification('Unable to generate payment file.', 'error');
    } finally {
      setIsGeneratingPaymentFile(false);
    }
  };

  const submitPaymentFileReview = async (paymentFileId, actionType) => {
    if (!selectedPaymentFile) {
      showNotification('Select a payment file first.', 'warning');
      return;
    }

    setIsSubmittingReview(true);
    try {
      const response = await fetch(`/api/rest/central-payment/${paymentFileId}/review/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          edits: reviewEdits,
          rejected_ids: reviewRejectedIds,
          rejection_reason: reviewReason,
        }),
      });
      const data = await response.json();
      if (response.ok) {
        setSelectedPaymentFile(data.payment_file || null);
        showNotification('Payment file review submitted successfully.', 'success');
        fetchPaymentFiles();
      } else {
        showNotification(data.error || 'Unable to submit review.', 'error');
      }
    } catch (error) {
      console.error('Error submitting review:', error);
      showNotification('Unable to submit review.', 'error');
    } finally {
      setIsSubmittingReview(false);
    }
  };

  const uploadBankPortalFile = async (file) => {
    if (!selectedPaymentFile || !file) return;
    setIsUploadingBankFile(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const response = await fetch(`/api/rest/central-payment/${selectedPaymentFile.id}/bank-file/`, { method: 'POST', body: formData });
      const data = await response.json();
      if (response.ok) {
        setSelectedPaymentFile(data.payment_file);
        showNotification(data.payment_file.bank_file_matches ? 'Bank file matches the approved file.' : 'Bank file does not match the approved file.', data.payment_file.bank_file_matches ? 'success' : 'warning');
      } else showNotification(data.error || 'Unable to compare bank file.', 'error');
    } catch (error) {
      showNotification('Unable to upload bank portal file.', 'error');
    } finally {
      setIsUploadingBankFile(false);
      if (bankFileInputRef.current) bankFileInputRef.current.value = '';
    }
  };

  const submitApReview = async (action) => {
    const rejectedItems = Object.fromEntries(
      reviewRejectedIds.map((invoiceId) => [invoiceId, (apRejectedComments[invoiceId] || '').trim()])
    );
    if (action === 'reject' && reviewRejectedIds.length === 0) {
      showNotification('Select at least one line item to reject.', 'warning');
      return;
    }
    if (action === 'reject' && Object.values(rejectedItems).some((comment) => !comment)) {
      showNotification('Enter a rejection comment for every selected line item.', 'warning');
      return;
    }
    setIsSubmittingReview(true);
    try {
      const response = await fetch(`/api/rest/central-payment/${selectedPaymentFile.id}/ap-review/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action, rejected_items: action === 'reject' ? rejectedItems : {} }),
      });
      const data = await response.json();
      if (response.ok) {
        setSelectedPaymentFile(data.payment_file);
        setApRejectedComments({});
        setReviewRejectedIds([]);
        showNotification(action === 'approve' ? 'Payment file approved by AP Team.' : 'AP line-item rejections submitted.', 'success');
        fetchPaymentFiles();
      } else showNotification(data.error || 'Unable to submit AP review.', 'error');
    } catch (error) {
      console.error('Error submitting AP review:', error);
      showNotification('Unable to submit AP review.', 'error');
    } finally {
      setIsSubmittingReview(false);
    }
  };

  const regenerateRejectedPaymentFile = async () => {
    if (!selectedPaymentFile) return;
    setIsRegeneratingPaymentFile(true);
    try {
      const response = await fetch(`/api/rest/central-payment/${selectedPaymentFile.id}/regenerate/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invoice_ids: regenerationInvoiceIds }),
      });
      const data = await response.json();
      if (response.ok) {
        showNotification('A new payment file was generated with only the rejected invoice rows.', 'success');
        setSelectedPaymentFile(data.payment_file || null);
        setPaymentFilesStatusFilter('PENDING');
        fetchPaymentFiles();
      } else {
        showNotification(data.error || 'Unable to regenerate payment file.', 'error');
      }
    } catch (error) {
      console.error('Error regenerating payment file:', error);
      showNotification('Unable to regenerate payment file.', 'error');
    } finally {
      setIsRegeneratingPaymentFile(false);
    }
  };

  const toggleRegenerationInvoice = (invoiceId) => {
    setRegenerationInvoiceIds((current) => current.includes(invoiceId)
      ? current.filter((id) => id !== invoiceId)
      : [...current, invoiceId]);
  };

  const onFilesSelected = (event) => {
    const selectedFiles = Array.from(event.target.files || []);
    const supportedFiles = selectedFiles.filter((file) => {
      const fileName = (file.name || '').toLowerCase();
      return !fileName.startsWith('.') && /\.(pdf|png|jpe?g|tiff?|bmp|webp)$/.test(fileName);
    });
    if (supportedFiles.length === 0) {
      showNotification('No supported invoice files found. Select PDF or image files.', 'warning');
      return;
    }
    if (supportedFiles.length !== selectedFiles.length) {
      showNotification(`${selectedFiles.length - supportedFiles.length} hidden or unsupported file(s) ignored.`, 'info');
    }
    executeFolderUpload(supportedFiles);
  };

  const executeFolderUpload = async (files) => {
    if (!invoiceDataReady) {
      showNotification("Get the due report first.", "warning");
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

  const renderReconciliationFlag = (row, fieldName) => {
    if (!row.invoice_scanned || row[fieldName] === null || row[fieldName] === undefined) return '—';
    return normalizeBooleanFlag(row[fieldName]) ? '✓' : '✕';
  };

  const getReconciliationTooltip = (row, fieldName) => {
    if (!row.invoice_scanned) return 'Invoice not scanned; this check has not run.';
    const values = row.reconciliation_details?.values || {};
    const ocr = values.ocr || {};
    const due = values.due_report || {};
    const labels = {
      invoice_number_matches: ['Invoice number', ocr.invoice_number, due.invoice_number],
      payable_amount_matches: ['Payable amount', ocr.payable_amount, due.payable_amount],
      goods_value_matches: ['Goods value', ocr.goods_value, due.goods_value],
      tax_amount_matches: ['Tax amount', ocr.tax_amount, due.tax_amount],
      tax_type_matches: ['Tax type', values.expected_tax_type, due.tax_type],
      vendor_gst_matches: ['Vendor GST', ocr.vendor_gst, due.vendor_gst],
      vendor_master_verified: ['Vendor master', ocr.vendor_gst, row.vendor_master_verified ? 'GST found in Vendor Master' : 'GST not found in Vendor Master'],
      store_gst_matches: ['Store GST', ocr.customer_gst, row.store_gst_matches ? 'GST matched' : 'GST did not match'],
      store_master_verified: ['Store master', ocr.customer_gst, row.store_master_verified ? 'GST found in Store Master' : 'GST not found in Store Master'],
    };
    const [label, scannedValue, reportValue] = labels[fieldName] || [fieldName, null, null];
    const result = renderReconciliationFlag(row, fieldName) === '✓' ? 'Matched' : 'Did not match';
    return `${label}\nScanned invoice: ${scannedValue ?? 'Missing'}\nDue report/master: ${reportValue ?? 'Missing'}\nResult: ${result}`;
  };

  const recoEligibleRows = invoiceRows.filter(
    (row) => row.invoice_scanned && VERIFIED_RECO_STATUSES.includes(normalizeInvoiceRecoStatus(row.invoice_reconciliation_status))
  );
  const freshInvoiceRows = recoEligibleRows.filter((row) => !row.is_payment_file_created && !row.payment_file_rejected && !row.manager_rejected);
  const rejectedInvoiceRows = recoEligibleRows.filter((row) => (row.payment_file_rejected || row.manager_rejected) && isInvoiceSelectableForPayment(row));
  const approvedGeneratedInvoiceRows = recoEligibleRows.filter((row) => row.is_payment_file_created && !row.manager_rejected);
  const unverifiedInvoiceRows = invoiceRows.filter(
    (row) => row.invoice_scanned && !VERIFIED_RECO_STATUSES.includes(normalizeInvoiceRecoStatus(row.invoice_reconciliation_status))
  );
  const unscannedInvoiceRows = invoiceRows.filter((row) => !row.invoice_scanned);
  const selectableInvoiceCount = invoiceRows.filter((row) => isInvoiceSelectableForPayment(row)).length;

  const getInvoiceRowStatusText = (row) => {
    if (!row.invoice_scanned) return 'Unscanned';
    if (!VERIFIED_RECO_STATUSES.includes(normalizeInvoiceRecoStatus(row.invoice_reconciliation_status))) {
      return 'Scanned - Unverified';
    }
    if (row.payment_file_rejected || row.manager_rejected) return `${row.payment_file_rejection_level || 'Manager'} rejected - available`;
    if (row.is_payment_file_created) return 'Already Created';
    return row.status || 'Pending';
  };

  const renderInvoiceSectionRows = (rows, emptyMessage, sectionKeyPrefix) => {
    if (collapsedInvoiceSections[sectionKeyPrefix]) return null;
    if (rows.length === 0) {
      return (
        <tr key={`${sectionKeyPrefix}-empty`}>
          <td colSpan={7} style={{ padding: '14px 12px', color: 'var(--text-secondary)', fontStyle: 'italic' }}>
            {emptyMessage}
          </td>
        </tr>
      );
    }

    return rows.map((row) => (
      <tr key={`${sectionKeyPrefix}-${row.id}`} style={{ backgroundColor: row.is_payment_file_created ? 'rgba(82, 196, 26, 0.08)' : 'transparent' }}>
        <td style={{ padding: '12px' }}>
          <input
            type="checkbox"
            checked={selectedInvoiceIds.includes(row.id)}
            disabled={!isInvoiceSelectableForPayment(row)}
            onChange={() => toggleInvoiceSelection(row.id)}
          />
        </td>
        <td style={{ padding: '12px', fontFamily: 'monospace' }}>{row.id || '—'}</td>
        <td style={{ padding: '12px' }}>{row.invoice_no || '—'}</td>
        <td style={{ padding: '12px' }}>{row.gst_number || '—'}</td>
        <td style={{ padding: '12px' }}>{row.supplier_name || '—'}</td>
        <td style={{ padding: '12px', textAlign: 'right' }}>{row.balance_amount || row.bill_amount || row.net_balance || '—'}</td>
        <td style={{ padding: '12px' }}>
          {getInvoiceRowStatusText(row)}
        </td>
      </tr>
    ));
  };

  const renderInvoiceSectionHeader = (sectionKey, label, count, accentColor = 'var(--primary-accent)') => (
    <tr>
      <td colSpan={7} style={{ padding: 0, backgroundColor: 'var(--background-secondary)', color: 'var(--text-primary)', fontWeight: '700', position: 'sticky', top: '49px', zIndex: 2, borderTop: '1px solid var(--card-border)', borderBottom: '1px solid var(--card-border)' }}>
        <button
          type="button"
          onClick={() => setCollapsedInvoiceSections((current) => ({ ...current, [sectionKey]: !current[sectionKey] }))}
          title={collapsedInvoiceSections[sectionKey] ? `Expand ${label}` : `Collapse ${label}`}
          aria-expanded={!collapsedInvoiceSections[sectionKey]}
          style={{ width: '100%', padding: '10px 12px', border: 'none', borderLeft: `4px solid ${accentColor}`, background: 'transparent', color: 'inherit', font: 'inherit', cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center', textAlign: 'left' }}
        >
          <span>{label} <span style={{ color: 'var(--text-secondary)', fontWeight: '600' }}>({count})</span></span>
          <span aria-hidden="true" style={{ color: 'var(--text-secondary)', fontSize: '1rem', lineHeight: 1 }}>{collapsedInvoiceSections[sectionKey] ? '▾' : '▴'}</span>
        </button>
      </td>
    </tr>
  );


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

  const FeatureCard = ({ iconSvg, title, description, onClick, isComingSoon, disabled = false, variant = 'default', innerActionLabel, onInnerAction }) => (
    <div
      onClick={!isComingSoon && !isUploading && !isDueReportFetching && !disabled ? onClick : undefined}
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
        cursor: (!isComingSoon && onClick && !isUploading && !isDueReportFetching && !disabled) ? 'pointer' : 'default',
        position: 'relative',
        opacity: (isComingSoon || disabled || (isUploading && title === "Upload Scanned Copy") || (isDueReportFetching && title === "Get Due Report")) ? 0.7 : 1,
        borderColor: variant === 'danger' ? '#ff4d4f' : variant === 'success' ? '#52c41a' : 'var(--card-border)'
      }}
      onMouseEnter={(e) => {
         if(!isComingSoon && onClick && !isUploading && !isDueReportFetching && !disabled) {
             e.currentTarget.style.transform = 'translateY(-5px)';
             e.currentTarget.style.boxShadow = '0 8px 16px var(--shadow-color)';
         }
      }}
      onMouseLeave={(e) => {
         if(!isComingSoon && onClick && !isUploading && !isDueReportFetching && !disabled) {
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

      {innerActionLabel && onInnerAction && (
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onInnerAction();
          }}
          disabled={isDueReportFetching}
          style={{ marginTop: '12px', padding: '9px 16px', borderRadius: '8px', border: '1px solid var(--primary-accent)', backgroundColor: 'transparent', color: 'var(--primary-accent)', fontWeight: 700, cursor: isDueReportFetching ? 'wait' : 'pointer', opacity: isDueReportFetching ? 0.65 : 1 }}
        >
          {innerActionLabel}
        </button>
      )}

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

      {isDueReportFetching && title === "Get Due Report" && (
          <div style={{ marginTop: '15px', fontSize: '0.8rem', color: 'var(--primary-accent)', fontWeight: 'bold' }}>
              Fetching due report...
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
      if(statusStr === 'MANUAL_REVIEW') return 'Scanned - Needs Review';
      if(statusStr === 'NO_MATCH') return 'Scanned - No Match';
      if(statusStr === 'UNVERIFIED') return 'Scanned - Not Verified';
      if(statusStr === 'PENDING') return 'Pending Scan/Reconciliation';

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
          case 'APPROVED':
              return { bg: 'transparent', text: 'var(--success)' };
          case 'FAILED':
          case 'NO_MATCH':
          case 'REJECTED':
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

  const getPaymentWorkflowMeta = (status) => {
      switch (status) {
          case 'APPROVED':
              return { label: 'Approved', color: 'var(--success)' };
          case 'REJECTED':
              return { label: 'Rejected', color: 'var(--danger)' };
          case 'PAID':
              return { label: 'Paid', color: '#8b5cf6' };
          default:
              return { label: 'Waiting', color: 'var(--primary-accent)' };
      }
  };

  const getPaymentRowReviewMeta = (row) => {
      if (row?.is_rejected) {
          return { label: 'Rejected', color: 'var(--danger)' };
      }
      if (row?.is_approved) {
          return { label: 'Approved', color: 'var(--success)' };
      }
      return { label: 'Waiting', color: 'var(--primary-accent)' };
  };

      const getPaymentFileRowAmountDisplay = (row) => {
        const rawValue = row?.amount ?? row?.balance_amount ?? row?.bill_amount ?? row?.net_balance;
        if (rawValue === null || rawValue === undefined || rawValue === '') return '—';
        const numericValue = typeof rawValue === 'number' ? rawValue : parseFloat(rawValue);
        return Number.isFinite(numericValue) ? numericValue.toFixed(2) : rawValue;
      };

  const renderContent = () => {
    switch (role) {
      case 'AP_TEAM':
        return (
          <div style={{ display: 'flex', gap: '2rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <FeatureCard
              iconSvg={FolderIcon}
              title="Review Approved Payment Files"
              description="Compare manager-approved files with bank portal files and review line items."
              onClick={() => handleAction("View Approved Payment Files")}
            />
          </div>
        );
      case 'STORE_ACCOUNTANT':
        return (
          <div style={{ display: 'flex', gap: '2rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <FeatureCard
              iconSvg={ReportIcon}
              title="Get Due Report"
              description={invoiceDataReady ? "Invoice data loaded from GetBills." : "Fetch the latest invoice data from GetBills."}
              onClick={() => handleAction("Get Due Report")}
              variant={invoiceDataReady ? "success" : "default"}
              innerActionLabel="View Due Report"
              onInnerAction={() => handleAction("View Due Report")}
            />

            <FeatureCard
              iconSvg={UploadIcon}
              title="Upload Scanned Copy"
              description={invoiceDataReady ? "Select a folder containing scanned invoice copies (PDFs, Images)." : "Get invoice data first to enable bill scanning."}
              onClick={() => handleAction("Upload Scanned Copy")}
              disabled={!invoiceDataReady}
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
              iconSvg={PaymentIcon}
              title="View Payment Files"
              description="See generated payment files and download approved outputs."
              onClick={() => handleAction("View Payment Files")}
            />

            <FeatureCard
              iconSvg={PaymentIcon}
              title="Generate Payment File"
              description="Generate final payment files for approved invoices."
              onClick={() => handleAction("Generate Payment File")}
            />
          </div>
        );
      case 'STORE_MANAGER':
        return (
          <div style={{ display: 'flex', gap: '2rem', justifyContent: 'center', flexWrap: 'wrap' }}>
            <FeatureCard
              iconSvg={ApproveIcon}
              title="Payment files waiting"
              description="View pending payment files from your accountants."
              variant="default"
              onClick={() => handleAction("View Waiting Payment Files")}
            />
            <FeatureCard
              iconSvg={RejectIcon}
              title="Approved payment files"
              description="View payment files that have already been approved."
              variant="success"
              onClick={() => handleAction("View Approved Payment Files")}
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

      {isDueReportModalOpen && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10001, padding: '4px' }}>
          <div style={{ width: 'calc(100vw - 8px)', height: 'calc(100vh - 8px)', maxWidth: 'none', maxHeight: 'none', boxSizing: 'border-box', backgroundColor: 'var(--card-background)', borderRadius: '6px', border: '1px solid var(--card-border)', padding: '7px', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <div style={{ minHeight: '28px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '5px' }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px', minWidth: 0 }}>
                <h2 style={{ margin: 0, color: 'var(--text-primary)', fontSize: '17px', lineHeight: '22px' }}>Due Report</h2>
                <span style={{ color: 'var(--text-secondary)', fontSize: '12px', whiteSpace: 'nowrap' }}>{dueReportPagination.total_items} invoices · reconciled first</span>
              </div>
              <button onClick={() => setIsDueReportModalOpen(false)} aria-label="Close due report" style={{ width: '26px', height: '26px', padding: 0, border: 0, background: 'transparent', color: 'var(--text-secondary)', fontSize: '20px', lineHeight: '24px', cursor: 'pointer' }}>×</button>
            </div>
            <div style={{ minHeight: '31px', display: 'flex', alignItems: 'center', gap: '5px', flexWrap: 'nowrap', marginBottom: '5px' }}>
              <input
                value={dueReportSearch}
                onChange={(event) => setDueReportSearch(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') fetchDueReport({ notify: false, page: 1 }); }}
                placeholder="Search invoice, vendor GST or vendor name"
                style={{ flex: '1 1 260px', minWidth: '180px', height: '30px', boxSizing: 'border-box', padding: '4px 8px', border: '1px solid var(--card-border)', borderRadius: '4px', background: 'var(--background-secondary)', color: 'var(--text-primary)', fontSize: '12px' }}
              />
              <select value={dueReportStoreFilter} onChange={(event) => setDueReportStoreFilter(event.target.value)} style={{ width: '190px', height: '30px', boxSizing: 'border-box', padding: '3px 6px', border: '1px solid var(--card-border)', borderRadius: '4px', background: 'var(--background-secondary)', color: 'var(--text-primary)', fontSize: '12px' }}>
                <option value="">All Royal Mart stores</option>
                {dueReportStores.map((store) => <option key={store} value={store}>{store}</option>)}
              </select>
              <select value={dueReportStatusFilter} onChange={(event) => setDueReportStatusFilter(event.target.value)} style={{ width: '190px', height: '30px', boxSizing: 'border-box', padding: '3px 6px', border: '1px solid var(--card-border)', borderRadius: '4px', background: 'var(--background-secondary)', color: 'var(--text-primary)', fontSize: '12px' }}>
                <option value="">All statuses</option>
                <option value="VERIFIED">Verified</option>
                <option value="MANUALLY_VERIFIED">Manually Verified</option>
                <option value="SCANNED_NOT_VERIFIED">Scanned - Not Verified (All)</option>
                <option value="MANUAL_REVIEW">Scanned - Needs Review</option>
                <option value="NO_MATCH">Scanned - No Match</option>
                <option value="UNVERIFIED">Scanned - Not Verified</option>
                <option value="PENDING">Pending Scan/Reconciliation</option>
                <option value="SCANNED">All Scanned</option>
                <option value="NOT_SCANNED">Not Scanned</option>
              </select>
              <button style={{ height: '30px', padding: '3px 10px', fontSize: '12px' }} onClick={() => fetchDueReport({ notify: false, page: 1 })}>Apply</button>
              <button onClick={() => {
                setDueReportSearch('');
                setDueReportStoreFilter('');
                setDueReportStatusFilter('');
                fetchDueReport({ notify: false, page: 1, q: '', store: '', status: '' });
              }} style={{ height: '30px', padding: '3px 10px', fontSize: '12px' }}>Clear</button>
            </div>
            <div style={{ overflow: 'auto', flex: '1 1 0', minHeight: 0, width: '100%', border: '1px solid var(--card-border)', borderRadius: '4px', backgroundColor: 'var(--card-background)' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'auto', minWidth: '1900px', fontSize: '12px', lineHeight: '16px' }}>
                <thead style={{ position: 'sticky', top: 0, zIndex: 2, backgroundColor: 'var(--background-secondary)' }}>
                  <tr>
                    {['Status', 'Invoice No', 'Invoice Date', 'Supplier', 'Vendor GST', 'Branch', 'Party Code', 'Voucher Amount', 'Report Goods Value', 'Report Tax Amount', 'Report Tax Code', 'Report Tax Type', 'TDS Amount', 'Due Days', 'Due Date', 'Payment Status', 'Payable'].map((label) => (
                      <th key={label} style={{ height: '26px', boxSizing: 'border-box', padding: '4px 7px', borderRight: '1px solid var(--card-border)', borderBottom: '1px solid var(--card-border)', textAlign: 'left', whiteSpace: 'nowrap', fontWeight: 600 }}>{label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {isDueReportFetching ? (
                    <tr><td colSpan={17} style={{ padding: '30px', textAlign: 'center' }}>Loading due report…</td></tr>
                  ) : dueReportRows.length === 0 ? (
                    <tr><td colSpan={17} style={{ padding: '30px', textAlign: 'center', color: 'var(--text-secondary)' }}>No invoices match the selected search and filters.</td></tr>
                  ) : dueReportRows.map((row) => (
                    <tr key={row.id} onClick={() => setSelectedDueReportRow(row)} title="View all invoice details" style={{ height: '24px', cursor: 'pointer' }}>
                      <td style={{ boxSizing: 'border-box', padding: '3px 7px', borderRight: '1px solid var(--card-border)', borderBottom: '1px solid var(--card-border)', whiteSpace: 'nowrap', fontWeight: 600, color: row.invoice_scanned ? getStatusColor(row.invoice_reconciliation_status).text : 'var(--text-secondary)' }}>{row.invoice_scanned ? formatStatus(row.invoice_reconciliation_status) : 'Not Scanned'}</td>
                      {[
                        [row.invoice_no, 'invoice_number_matches'],
                        [row.invoice_date, null],
                        [row.supplier_name, null],
                        [row.gst_number, 'vendor_gst_matches'],
                        [row.location_name, null],
                        [row.party_code, null],
                        [row.bill_amount, null],
                        [row.goods_value, 'goods_value_matches'],
                        [row.tax_amount, 'tax_amount_matches'],
                        [row.tax_code, null],
                        [row.tax_type, 'tax_type_matches'],
                        [row.tds_amount, null],
                        [row.no_of_days, null],
                        [row.due_date, null],
                        [row.payment_status, null],
                        [row.payable, 'payable_amount_matches'],
                      ].map(([value, matchField], index) => {
                        const isMismatch = row.invoice_scanned && matchField && row[matchField] !== null && row[matchField] !== undefined && !normalizeBooleanFlag(row[matchField]);
                        return (
                          <td key={index} title={isMismatch ? getReconciliationTooltip(row, matchField) : undefined} style={{ boxSizing: 'border-box', padding: '3px 7px', borderRight: '1px solid var(--card-border)', borderBottom: '1px solid var(--card-border)', whiteSpace: 'nowrap', color: isMismatch ? '#d97706' : undefined, fontWeight: isMismatch ? 700 : undefined }}>{value ?? '—'}</td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ minHeight: '28px', display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', marginTop: '4px', fontSize: '12px' }}>
              <button style={{ height: '26px', padding: '2px 9px', fontSize: '12px' }} disabled={!dueReportPagination.has_previous || isDueReportFetching} onClick={() => fetchDueReport({ notify: false, page: dueReportPagination.current_page - 1 })}>Previous</button>
              <span style={{ color: 'var(--text-primary)' }}>Page {dueReportPagination.current_page} / {dueReportPagination.total_pages}</span>
              <button style={{ height: '26px', padding: '2px 9px', fontSize: '12px' }} disabled={!dueReportPagination.has_next || isDueReportFetching} onClick={() => fetchDueReport({ notify: false, page: dueReportPagination.current_page + 1 })}>Next</button>
            </div>
          </div>
        </div>
      )}

      {selectedDueReportRow && (
        <div style={{ position: 'fixed', inset: 0, backgroundColor: 'rgba(0,0,0,0.68)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 10002, padding: '1rem' }} onClick={() => setSelectedDueReportRow(null)}>
          <div onClick={(event) => event.stopPropagation()} style={{ width: 'min(1000px, 96vw)', maxHeight: '90vh', overflowY: 'auto', background: 'var(--card-background)', border: '1px solid var(--card-border)', borderRadius: '12px', padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '1rem', marginBottom: '20px' }}>
              <div>
                <h2 style={{ margin: 0, color: 'var(--text-primary)' }}>Invoice {selectedDueReportRow.invoice_no || 'Details'}</h2>
                <p style={{ margin: '6px 0 0', color: 'var(--text-secondary)' }}>{selectedDueReportRow.supplier_name || 'Unknown vendor'}</p>
              </div>
              <button onClick={() => setSelectedDueReportRow(null)} aria-label="Close invoice details" style={{ border: 0, background: 'transparent', color: 'var(--text-secondary)', fontSize: '1.5rem', cursor: 'pointer' }}>×</button>
            </div>
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '18px' }}>
              <span style={{ padding: '6px 10px', borderRadius: '999px', background: 'var(--background-secondary)', color: getStatusColor(selectedDueReportRow.invoice_reconciliation_status).text, fontWeight: 700 }}>{selectedDueReportRow.invoice_scanned ? formatStatus(selectedDueReportRow.invoice_reconciliation_status) : 'Not Scanned'}</span>
            </div>

            <h3 style={{ color: 'var(--text-primary)', borderBottom: '1px solid var(--card-border)', paddingBottom: '8px' }}>Common fields and comparison</h3>
            <div style={{ overflowX: 'auto', border: '1px solid var(--card-border)', borderRadius: '8px' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '700px' }}>
                <thead style={{ background: 'var(--background-secondary)' }}>
                  <tr>{['Field', 'Due Report', 'Scanned Invoice', 'Result'].map((label) => <th key={label} style={{ padding: '10px', textAlign: 'left' }}>{label}</th>)}</tr>
                </thead>
                <tbody>
                  {COMMON_INVOICE_FIELDS.map(([label, dueField, scannedField, flagField]) => {
                    const details = selectedDueReportRow.reconciliation_details || {};
                    const scannedData = details.scanned_invoice || {};
                    const dueValue = selectedDueReportRow[dueField];
                    const scannedValue = scannedField === 'expected_tax_type' ? details.values?.expected_tax_type : scannedData[scannedField];
                    if ((dueValue === null || dueValue === undefined || dueValue === '') && (scannedValue === null || scannedValue === undefined || scannedValue === '')) return null;
                    const flag = flagField ? renderReconciliationFlag(selectedDueReportRow, flagField) : '—';
                    return (
                      <tr key={label} style={{ borderTop: '1px solid var(--card-border)' }}>
                        <td style={{ padding: '10px', fontWeight: 700 }}>{label}</td>
                        <td style={{ padding: '10px', overflowWrap: 'anywhere' }}>{dueValue ?? '—'}</td>
                        <td style={{ padding: '10px', overflowWrap: 'anywhere' }}>{scannedValue ?? (selectedDueReportRow.invoice_scanned ? 'Missing' : 'Not scanned')}</td>
                        <td title={flagField ? getReconciliationTooltip(selectedDueReportRow, flagField) : ''} style={{ padding: '10px', fontWeight: 800, color: flag === '✓' ? 'var(--success)' : flag === '✕' ? 'var(--danger)' : 'var(--text-secondary)', cursor: flagField ? 'help' : 'default' }}>{flag}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))', gap: '20px', marginTop: '24px' }}>
              <section>
                <h3 style={{ color: 'var(--text-primary)', borderBottom: '1px solid var(--card-border)', paddingBottom: '8px' }}>Due-report-only details</h3>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '10px' }}>
                  {DUE_REPORT_ONLY_FIELDS.map(([fieldName, label]) => {
                    const value = selectedDueReportRow[fieldName];
                    if (value === null || value === undefined || value === '') return null;
                    return <div key={fieldName} style={{ padding: '10px', background: 'var(--background-secondary)', borderRadius: '8px', minWidth: 0 }}><div style={{ color: 'var(--text-secondary)', fontSize: '0.76rem', marginBottom: '4px' }}>{label}</div><div style={{ color: 'var(--text-primary)', fontWeight: 600, overflowWrap: 'anywhere' }}>{value}</div></div>;
                  })}
                </div>
              </section>

              <section>
                <h3 style={{ color: 'var(--text-primary)', borderBottom: '1px solid var(--card-border)', paddingBottom: '8px' }}>Scanned-invoice-only details</h3>
                {!selectedDueReportRow.invoice_scanned ? <p style={{ color: 'var(--text-secondary)' }}>Invoice not scanned.</p> : (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '10px' }}>
                    {SCANNED_INVOICE_ONLY_FIELDS.map(([fieldName, label]) => {
                      const details = selectedDueReportRow.reconciliation_details || {};
                      const value = fieldName === 'scanned_filename' ? details.scanned_filename : details.scanned_invoice?.[fieldName];
                      if (value === null || value === undefined || value === '') return null;
                      return <div key={fieldName} style={{ padding: '10px', background: 'var(--background-secondary)', borderRadius: '8px', minWidth: 0 }}><div style={{ color: 'var(--text-secondary)', fontSize: '0.76rem', marginBottom: '4px' }}>{label}</div><div style={{ color: 'var(--text-primary)', fontWeight: 600, overflowWrap: 'anywhere' }}>{value}</div></div>;
                    })}
                  </div>
                )}
              </section>
            </div>
          </div>
        </div>
      )}

      {/* Payment File Generation Modal */}
      {isPaymentFileModalOpen && (
        <div style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.6)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 10001,
            padding: '1rem'
        }}>
            <div style={{
                width: '100%',
                maxWidth: '1100px',
                maxHeight: '90vh',
                overflowY: 'auto',
                backgroundColor: 'var(--card-background)',
                borderRadius: '12px',
                boxShadow: '0 16px 40px rgba(0,0,0,0.25)',
                border: '1px solid var(--card-border)',
                padding: '24px',
                position: 'relative'
            }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                    <div>
                        <h2 style={{ margin: 0, color: 'var(--text-primary)' }}>Generate Payment File</h2>
                        <p style={{ margin: '8px 0 0', color: 'var(--text-secondary)' }}>
                          Select due-report invoices, choose a payment type, and generate a payment file with bank details lookups.
                        </p>
                    </div>
                    <button
                      onClick={() => setIsPaymentFileModalOpen(false)}
                      style={{
                          border: 'none',
                          background: 'transparent',
                          color: 'var(--text-secondary)',
                          fontSize: '1.5rem',
                          cursor: 'pointer'
                      }}
                      aria-label="Close payment file modal"
                    >
                      ×
                    </button>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <label htmlFor="paymentTypeSelect" style={{ fontWeight: '600', color: 'var(--text-primary)' }}>Payment Type</label>
                        <select
                          id="paymentTypeSelect"
                          value={paymentType}
                          onChange={(e) => setPaymentType(e.target.value)}
                          style={{ padding: '10px 12px', borderRadius: '8px', border: '1px solid var(--card-border)', backgroundColor: 'var(--background-secondary)', color: 'var(--text-primary)' }}
                        >
                            <option value="ICICI">ICICI</option>
                            <option value="SBI">SBI</option>
                        </select>
                        <label htmlFor="paymentFileFormatSelect" style={{ fontWeight: '600', color: 'var(--text-primary)', marginLeft: '0.5rem' }}>File Format</label>
                        <select
                          id="paymentFileFormatSelect"
                          value={paymentFileFormat}
                          onChange={(e) => setPaymentFileFormat(e.target.value)}
                          style={{ padding: '10px 12px', borderRadius: '8px', border: '1px solid var(--card-border)', backgroundColor: 'var(--background-secondary)', color: 'var(--text-primary)' }}
                        >
                            <option value="xlsx">Excel (.xlsx)</option>
                            <option value="csv">CSV (.csv)</option>
                        </select>
                    </div>
                    <button
                      onClick={toggleSelectAll}
                      disabled={selectableInvoiceCount === 0}
                      style={{
                          border: '1px solid var(--card-border)',
                          backgroundColor: 'var(--card-background)',
                          color: 'var(--text-primary)',
                          padding: '10px 16px',
                          borderRadius: '8px',
                          cursor: selectableInvoiceCount === 0 ? 'not-allowed' : 'pointer',
                          opacity: selectableInvoiceCount === 0 ? 0.7 : 1
                      }}
                    >
                      {selectedInvoiceIds.length === selectableInvoiceCount && selectableInvoiceCount > 0 ? 'Deselect All' : 'Select All'}
                    </button>
                </div>
                <div style={{ marginTop: '1.25rem', border: '1px solid var(--card-border)', borderRadius: '12px', overflow: 'auto', maxHeight: '58vh' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '760px' }}>
                        <thead style={{ backgroundColor: 'var(--background-secondary)', position: 'sticky', top: 0, zIndex: 4 }}>
                            <tr>
                              <th style={{ padding: '12px 12px', textAlign: 'left' }}></th>
                              <th style={{ padding: '12px 12px', textAlign: 'left' }}>ID</th>
                              <th style={{ padding: '12px 12px', textAlign: 'left' }}>Invoice</th>
                              <th style={{ padding: '12px 12px', textAlign: 'left' }}>GST</th>
                              <th style={{ padding: '12px 12px', textAlign: 'left' }}>Supplier</th>
                              <th style={{ padding: '12px 12px', textAlign: 'right' }}>Amount</th>
                              <th style={{ padding: '12px 12px', textAlign: 'left' }}>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {isFetchingInvoiceRows ? (
                                <tr>
                                  <td colSpan={7} style={{ padding: '30px 12px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                                      Loading invoice rows...
                                  </td>
                                </tr>
                            ) : invoiceRows.length === 0 ? (
                                <tr>
                                  <td colSpan={7} style={{ padding: '30px 12px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                                      No invoice rows available for payment file generation.
                                  </td>
                                </tr>
                            ) : (
                              <>
                                {renderInvoiceSectionHeader('fresh', 'Fresh Invoices (Scanned + Verified/Manually Verified)', freshInvoiceRows.length, 'var(--success)')}
                                {renderInvoiceSectionRows(freshInvoiceRows, 'No fresh invoices.', 'fresh')}

                                {renderInvoiceSectionHeader('rejected', 'Rejected Invoices', rejectedInvoiceRows.length, 'var(--danger)')}
                                {renderInvoiceSectionRows(rejectedInvoiceRows, 'No rejected invoices.', 'rejected')}

                                {renderInvoiceSectionHeader('unverified', 'Unverified Invoices (Scanned but not verified)', unverifiedInvoiceRows.length, '#d97706')}
                                {renderInvoiceSectionRows(unverifiedInvoiceRows, 'No unverified invoices.', 'unverified')}

                                {renderInvoiceSectionHeader('unscanned', 'Unscanned Invoices', unscannedInvoiceRows.length)}
                                {renderInvoiceSectionRows(unscannedInvoiceRows, 'No unscanned invoices.', 'unscanned')}

                                {renderInvoiceSectionHeader('approved', 'Already Generated & Approved Invoices', approvedGeneratedInvoiceRows.length, 'var(--success)')}
                                {renderInvoiceSectionRows(approvedGeneratedInvoiceRows, 'No already-generated approved invoices.', 'approved')}
                              </>
                            )}
                        </tbody>
                    </table>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginTop: '1.5rem' }}>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'center' }}>
                        <button
                          onClick={generatePaymentFile}
                          disabled={isGeneratingPaymentFile || selectedInvoiceIds.length === 0}
                          style={{
                              border: 'none',
                              backgroundColor: selectedInvoiceIds.length === 0 ? 'var(--background-secondary)' : 'var(--primary-accent)',
                              color: selectedInvoiceIds.length === 0 ? 'var(--text-secondary)' : '#fff',
                              padding: '12px 20px',
                              borderRadius: '8px',
                              cursor: selectedInvoiceIds.length === 0 ? 'not-allowed' : 'pointer'
                          }}
                        >
                          {isGeneratingPaymentFile ? 'Generating...' : 'Generate Payment File'}
                        </button>
                        <span style={{ color: 'var(--text-secondary)' }}>
                            {selectedInvoiceIds.length} invoice(s) selected.
                        </span>
                    </div>
                    {paymentFileResult && (
                        <div style={{ padding: '16px', borderRadius: '10px', backgroundColor: 'var(--background-secondary)', border: '1px solid var(--card-border)' }}>
                            <strong style={{ display: 'block', marginBottom: '0.5rem' }}>Payment file created:</strong>
                            <div style={{ display: 'grid', gap: '8px', fontSize: '0.95rem' }}>
                                <span>ID: {paymentFileResult.id}</span>
                                <span>Type: {paymentFileResult.payment_type}</span>
                                <span>Total Rows: {paymentFileResult.total_files}</span>
                                <span>Status: {paymentFileResult.status}</span>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginTop: '0.25rem' }}>
                                  {paymentFileResult.download_url && (
                                    <a href={paymentFileResult.download_url} target="_blank" rel="noreferrer" style={{ color: 'var(--primary-accent)', fontWeight: '600', display: 'inline-block', padding: '8px 12px', borderRadius: '8px', backgroundColor: 'var(--card-background)', border: '1px solid var(--card-border)' }}>
                                      Download {paymentFileResult.file_format === 'csv' ? 'CSV' : 'Excel'} file
                                    </a>
                                  )}
                                  {paymentFileResult.id && (
                                    <button
                                      type="button"
                                      onClick={() => openPaymentFilePreview(paymentFileResult.id)}
                                      style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--card-border)', backgroundColor: 'var(--card-background)', color: 'var(--text-primary)', cursor: 'pointer' }}
                                    >
                                      View
                                    </button>
                                  )}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
      )}

      {isPaymentFilesModalOpen && (
        <div style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.65)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 10002,
            padding: '1rem'
        }}>
            <div style={{
                width: '95%',
                maxWidth: '1400px',
                maxHeight: '95vh',
                overflowY: 'auto',
                backgroundColor: 'var(--card-background)',
                borderRadius: '16px',
                boxShadow: '0 18px 50px rgba(0,0,0,0.35)',
                border: '1px solid var(--card-border)',
                padding: '24px',
                position: 'relative'
            }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                    <div>
                        <h2 style={{ margin: 0, color: 'var(--text-primary)' }}>
                          {paymentFilesStatusFilter === 'APPROVED'
                            ? 'Approved payment files'
                            : paymentFilesStatusFilter === 'REJECTED'
                              ? 'Rejected payment files'
                              : 'Payment file review'}
                        </h2>
                        <p style={{ margin: '8px 0 0', color: 'var(--text-secondary)' }}>
                          {paymentFilesStatusFilter === 'APPROVED'
                            ? 'View payment files already approved for payout.'
                            : paymentFilesStatusFilter === 'REJECTED'
                              ? 'Review files that were rejected and can be regenerated or rechecked.'
                              : 'Review payment files from your accountants. You can approve everything, reject selected rows, or make edits before submitting.'}
                        </p>
                    </div>
                    <button
                      onClick={closePaymentFilesModal}
                      style={{
                          border: 'none',
                          background: 'transparent',
                          color: 'var(--text-secondary)',
                          fontSize: '1.75rem',
                          cursor: 'pointer'
                      }}
                      aria-label="Close payment files modal"
                    >
                      ×
                    </button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'minmax(360px, 0.9fr) minmax(560px, 1.4fr)', gap: '1rem', marginTop: '1.5rem', alignItems: 'start' }}>
                    <div style={{ backgroundColor: 'var(--background-secondary)', borderRadius: '12px', border: '1px solid var(--card-border)', overflow: 'hidden', minHeight: '70vh' }}>
                        <div style={{ padding: '16px', borderBottom: '1px solid var(--card-border)' }}>
                            <strong style={{ color: 'var(--text-primary)' }}>Payment File List</strong>
                            <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
                              <button
                                onClick={() => setPaymentFilesStatusFilter('PENDING')}
                                style={{
                                  padding: '8px 14px',
                                  borderRadius: '999px',
                                  border: paymentFilesStatusFilter === 'PENDING' ? '1px solid var(--primary-accent)' : '1px solid var(--card-border)',
                                  backgroundColor: paymentFilesStatusFilter === 'PENDING' ? 'var(--primary-accent)' : 'transparent',
                                  color: paymentFilesStatusFilter === 'PENDING' ? '#fff' : 'var(--text-primary)',
                                  cursor: 'pointer'
                                }}
                              >
                                Waiting
                              </button>
                              <button
                                onClick={() => setPaymentFilesStatusFilter('APPROVED')}
                                style={{
                                  padding: '8px 14px',
                                  borderRadius: '999px',
                                  border: paymentFilesStatusFilter === 'APPROVED' ? '1px solid var(--primary-accent)' : '1px solid var(--card-border)',
                                  backgroundColor: paymentFilesStatusFilter === 'APPROVED' ? 'var(--primary-accent)' : 'transparent',
                                  color: paymentFilesStatusFilter === 'APPROVED' ? '#fff' : 'var(--text-primary)',
                                  cursor: 'pointer'
                                }}
                              >
                                Approved
                              </button>
                              <button
                                onClick={() => setPaymentFilesStatusFilter('REJECTED')}
                                style={{
                                  padding: '8px 14px',
                                  borderRadius: '999px',
                                  border: paymentFilesStatusFilter === 'REJECTED' ? '1px solid var(--primary-accent)' : '1px solid var(--card-border)',
                                  backgroundColor: paymentFilesStatusFilter === 'REJECTED' ? 'var(--primary-accent)' : 'transparent',
                                  color: paymentFilesStatusFilter === 'REJECTED' ? '#fff' : 'var(--text-primary)',
                                  cursor: 'pointer'
                                }}
                              >
                                Rejected
                              </button>
                              <select
                                value={paymentFilesAccountantFilter}
                                onChange={(e) => setPaymentFilesAccountantFilter(e.target.value)}
                                style={{ padding: '8px 12px', borderRadius: '10px', border: '1px solid var(--card-border)', background: 'var(--card-background)', color: 'var(--text-primary)' }}
                              >
                                {accountantOptions.map((option) => (
                                  <option key={option.id} value={option.id}>{option.label}</option>
                                ))}
                              </select>
                            </div>
                            <div style={{ marginTop: '0.85rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                              <div style={{ padding: '8px 10px', borderRadius: '10px', backgroundColor: 'var(--card-background)', border: '1px solid var(--card-border)', minWidth: '96px' }}>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.4px' }}>Waiting</div>
                                <div style={{ fontWeight: '700', color: 'var(--primary-accent)' }}>{paymentFiles.filter((file) => file.payment_status === 'PENDING').length}</div>
                              </div>
                              <div style={{ padding: '8px 10px', borderRadius: '10px', backgroundColor: 'var(--card-background)', border: '1px solid var(--card-border)', minWidth: '96px' }}>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.4px' }}>Approved</div>
                                <div style={{ fontWeight: '700', color: 'var(--success)' }}>{paymentFiles.filter((file) => file.payment_status === 'APPROVED').length}</div>
                              </div>
                              <div style={{ padding: '8px 10px', borderRadius: '10px', backgroundColor: 'var(--card-background)', border: '1px solid var(--card-border)', minWidth: '96px' }}>
                                <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textTransform: 'uppercase', letterSpacing: '0.4px' }}>Rejected</div>
                                <div style={{ fontWeight: '700', color: 'var(--danger)' }}>{paymentFiles.filter((file) => file.payment_status === 'REJECTED').length}</div>
                              </div>
                            </div>
                            <p style={{ margin: '8px 0 0', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
                                {isFetchingPaymentFiles ? 'Loading files...' : `${filteredPaymentFiles.length} file(s) match current filters`}
                            </p>
                        </div>
                        <div style={{ maxHeight: '70vh', overflowY: 'auto' }}>
                            {filteredPaymentFiles.length === 0 && !isFetchingPaymentFiles ? (
                              <div style={{ padding: '18px', color: 'var(--text-secondary)' }}>No payment files found.</div>
                            ) : (
                              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead style={{ backgroundColor: 'var(--background-secondary)' }}>
                                  <tr>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>ID</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Type</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Created By</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Manager Review</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>AP Team Review</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Created At</th>
                                    <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Action</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {filteredPaymentFiles.map((paymentFile) => {
                                    const managerReviewMeta = getPaymentWorkflowMeta(paymentFile.manager_review_status);
                                    const apReviewMeta = getPaymentWorkflowMeta(paymentFile.ap_review_status);
                                    return (
                                      <tr
                                        key={paymentFile.id}
                                        onClick={() => fetchPaymentFileDetail(paymentFile.id)}
                                        style={{
                                          cursor: 'pointer',
                                          backgroundColor: selectedPaymentFile?.id === paymentFile.id ? 'rgba(82, 196, 26, 0.08)' : 'transparent'
                                        }}
                                      >
                                        <td style={{ padding: '12px', borderBottom: '1px solid var(--card-border)' }}>{paymentFile.id}</td>
                                        <td style={{ padding: '12px', borderBottom: '1px solid var(--card-border)' }}>{paymentFile.payment_type}</td>
                                        <td style={{ padding: '12px', borderBottom: '1px solid var(--card-border)' }}>{paymentFile.created_by || '—'}</td>
                                        <td style={{ padding: '12px', borderBottom: '1px solid var(--card-border)' }}>
                                          <span style={{ color: managerReviewMeta.color, fontWeight: '700' }}>{managerReviewMeta.label}</span>
                                        </td>
                                        <td style={{ padding: '12px', borderBottom: '1px solid var(--card-border)' }}>
                                          <span style={{ color: apReviewMeta.color, fontWeight: '700' }}>{apReviewMeta.label}</span>
                                        </td>
                                        <td style={{ padding: '12px', borderBottom: '1px solid var(--card-border)' }}>{paymentFile.created_at ? new Date(paymentFile.created_at).toLocaleString() : '—'}</td>
                                        <td style={{ padding: '12px', borderBottom: '1px solid var(--card-border)' }}>
                                          <button
                                            type="button"
                                            onClick={(event) => {
                                              event.stopPropagation();
                                              openPaymentFilePreview(paymentFile.id);
                                            }}
                                            style={{ padding: '8px 12px', borderRadius: '8px', border: '1px solid var(--card-border)', backgroundColor: 'var(--card-background)', color: 'var(--text-primary)', cursor: 'pointer' }}
                                          >
                                            View Payment File
                                          </button>
                                        </td>
                                      </tr>
                                    );
                                  })}
                                </tbody>
                              </table>
                            )}
                        </div>
                    </div>

                    <div style={{ backgroundColor: 'var(--background-secondary)', borderRadius: '12px', border: '1px solid var(--card-border)', overflow: 'hidden' }}>
                        <div style={{ padding: '16px', borderBottom: '1px solid var(--card-border)' }}>
                            <strong style={{ color: 'var(--text-primary)' }}>Selected File</strong>
                        </div>
                        <div style={{ padding: '16px' }}>
                            {isFetchingSelectedPaymentFile ? (
                                <div style={{ color: 'var(--text-secondary)' }}>Loading...</div>
                            ) : selectedPaymentFile ? (
                                <>
                                    {/* File meta */}
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
                                        <div><div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>ID</div><div style={{ fontWeight: '700' }}>{selectedPaymentFile.id}</div></div>
                                        <div><div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Type</div><div style={{ fontWeight: '700' }}>{selectedPaymentFile.payment_type}</div></div>
                                        <div><div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Manager Review</div><div style={{ fontWeight: '700', color: getStatusColor(selectedPaymentFile.manager_review_status).text }}>{selectedPaymentFile.manager_review_status || 'PENDING'}</div></div>
                                        <div><div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>AP Review</div><div style={{ fontWeight: '700', color: selectedPaymentFile.is_ap_approved ? 'var(--success)' : selectedPaymentFile.is_ap_rejected ? 'var(--danger)' : 'var(--text-secondary)' }}>{selectedPaymentFile.is_ap_approved ? 'AP Approved' : selectedPaymentFile.is_ap_rejected ? 'AP Rejected' : 'Pending AP Review'}</div></div>
                                        <div><div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Created By</div><div style={{ fontWeight: '700' }}>{selectedPaymentFile.created_by || '—'}</div></div>
                                        <div><div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Rows</div><div style={{ fontWeight: '700' }}>{(selectedPaymentFile.rows || []).length}</div></div>
                                    </div>

                                    {/* Row status pills */}
                                    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginBottom: '1rem' }}>
                                      <div style={{ padding: '8px 12px', borderRadius: '10px', backgroundColor: 'var(--card-background)', border: '1px solid var(--card-border)' }}>
                                        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Waiting </span>
                                        <strong style={{ color: 'var(--primary-accent)' }}>{(selectedPaymentFile.rows || []).filter((r) => !r.is_approved && !r.is_rejected).length}</strong>
                                      </div>
                                      <div style={{ padding: '8px 12px', borderRadius: '10px', backgroundColor: 'var(--card-background)', border: '1px solid var(--card-border)' }}>
                                        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Approved </span>
                                        <strong style={{ color: 'var(--success)' }}>{(selectedPaymentFile.rows || []).filter((r) => r.is_approved).length}</strong>
                                      </div>
                                      <div style={{ padding: '8px 12px', borderRadius: '10px', backgroundColor: 'var(--card-background)', border: '1px solid var(--card-border)' }}>
                                        <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Rejected </span>
                                        <strong style={{ color: 'var(--danger)' }}>{(selectedPaymentFile.rows || []).filter((r) => r.is_rejected).length}</strong>
                                      </div>
                                    </div>

                                    {/* Actions */}
                                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1.25rem' }}>
                                      <button
                                        type="button"
                                        onClick={() => openPaymentFilePreview(selectedPaymentFile.id)}
                                        style={{ padding: '10px 16px', borderRadius: '10px', border: 'none', backgroundColor: 'var(--primary-accent)', color: '#fff', cursor: 'pointer', fontWeight: '600' }}
                                      >
                                        View Generated File
                                      </button>
                                      {selectedPaymentFile.download_url && (
                                        <a href={getFormattedDownloadUrl(selectedPaymentFile.download_url, 'xlsx')} target="_blank" rel="noreferrer" style={{ padding: '10px 16px', borderRadius: '10px', border: '1px solid var(--card-border)', backgroundColor: 'var(--card-background)', color: 'var(--primary-accent)', fontWeight: '600', textDecoration: 'none' }}>
                                          Download Excel
                                        </a>
                                      )}
                                      {selectedPaymentFile.download_url && (
                                        <a href={getFormattedDownloadUrl(selectedPaymentFile.download_url, 'csv')} target="_blank" rel="noreferrer" style={{ padding: '10px 16px', borderRadius: '10px', border: '1px solid var(--card-border)', backgroundColor: 'var(--card-background)', color: 'var(--primary-accent)', fontWeight: '600', textDecoration: 'none' }}>
                                          Download CSV
                                        </a>
                                      )}
                                      {selectedPaymentFile.can_regenerate && (
                                        <button
                                          type="button"
                                          onClick={regenerateRejectedPaymentFile}
                                          disabled={isRegeneratingPaymentFile || regenerationInvoiceIds.length === 0}
                                          style={{ padding: '10px 16px', borderRadius: '10px', border: 'none', backgroundColor: 'var(--danger)', color: '#fff', cursor: 'pointer', fontWeight: '600', opacity: isRegeneratingPaymentFile ? 0.6 : 1 }}
                                        >
                                          {isRegeneratingPaymentFile ? 'Regenerating...' : `Generate New File (${regenerationInvoiceIds.length})`}
                                        </button>
                                      )}
                                      {role === 'AP_TEAM' && selectedPaymentFile.payment_status === 'APPROVED' && (
                                        <>
                                          <button type="button" onClick={() => bankFileInputRef.current?.click()} disabled={isUploadingBankFile} style={{ padding: '10px 16px', borderRadius: '10px', border: '1px solid var(--card-border)', backgroundColor: 'var(--card-background)', color: 'var(--primary-accent)', cursor: 'pointer', fontWeight: '600' }}>
                                            {isUploadingBankFile ? 'Comparing...' : 'Upload Bank Portal File'}
                                          </button>
                                          <input ref={bankFileInputRef} type="file" accept=".xlsx,.xls,.xlsm,.csv" style={{ display: 'none' }} onChange={(event) => uploadBankPortalFile(event.target.files?.[0])} />
                                        </>
                                      )}
                                    </div>

                                    {role === 'AP_TEAM' && selectedPaymentFile.bank_file_matches != null && (
                                      <div style={{ padding: '12px 16px', marginBottom: '1rem', borderRadius: '10px', border: `1px solid ${selectedPaymentFile.bank_file_matches ? 'var(--success)' : 'var(--danger)'}`, color: selectedPaymentFile.bank_file_matches ? 'var(--success)' : 'var(--danger)', fontWeight: '700' }}>
                                        {selectedPaymentFile.bank_file_matches ? 'Bank portal file matches the manager-approved file.' : 'Bank portal file does not match the manager-approved file.'}
                                        <div style={{ fontSize: '0.85rem', fontWeight: '400', marginTop: '4px' }}>
                                          Expected {selectedPaymentFile.bank_file_comparison?.expected_rows || 0}, uploaded {selectedPaymentFile.bank_file_comparison?.uploaded_rows || 0}, missing {selectedPaymentFile.bank_file_comparison?.missing_rows || 0}, unexpected {selectedPaymentFile.bank_file_comparison?.unexpected_rows || 0}.
                                        </div>
                                      </div>
                                    )}

                                    {(selectedPaymentFile.history || []).length > 0 && (
                                      <div style={{ marginBottom: '1.25rem', padding: '14px 16px', border: '1px solid var(--card-border)', borderRadius: '12px', backgroundColor: 'var(--card-background)' }}>
                                        <div style={{ fontWeight: '700', marginBottom: '10px' }}>Payment File History</div>
                                        {(selectedPaymentFile.history || []).map((event, index) => (
                                          <div key={`${event.event_type}-${event.created_at}-${index}`} style={{ padding: '9px 0', borderTop: index ? '1px solid var(--card-border)' : 'none', display: 'grid', gridTemplateColumns: '160px minmax(140px, 1fr) 2fr', gap: '12px', fontSize: '0.88rem' }}>
                                            <span style={{ fontWeight: '700' }}>{event.event_type.replaceAll('_', ' ')}</span>
                                            <span>{event.actor || 'System'}<br/><small style={{ color: 'var(--text-secondary)' }}>{event.created_at ? new Date(event.created_at).toLocaleString() : ''}</small></span>
                                            <span style={{ color: 'var(--text-secondary)' }}>
                                              {event.comment || event.metadata?.new_payment_file_id || (event.invoice_ids?.length ? `${event.invoice_ids.length} invoice(s)` : '—')}
                                            </span>
                                          </div>
                                        ))}
                                      </div>
                                    )}

                                    <div style={{ marginBottom: '1.25rem' }}>
                                      <div style={{ fontWeight: '600', color: 'var(--text-primary)', marginBottom: '0.75rem' }}>Invoice Line Items</div>
                                      {selectedPaymentFile.can_regenerate && (
                                        <div style={{ color: 'var(--text-secondary)', fontSize: '0.88rem', marginBottom: '0.75rem' }}>
                                          Approved invoices are selected by default. Rejected invoices are unchecked, but you can include them if needed.
                                        </div>
                                      )}
                                      <div style={{ border: '1px solid var(--card-border)', borderRadius: '12px', overflow: 'hidden', backgroundColor: 'var(--card-background)' }}>
                                        <div style={{ maxHeight: '340px', overflowY: 'auto', overflowX: 'auto' }}>
                                          <table style={{ width: '100%', minWidth: '860px', borderCollapse: 'collapse' }}>
                                            <thead style={{ backgroundColor: 'var(--background-secondary)', position: 'sticky', top: 0, zIndex: 1 }}>
                                              <tr>
                                                {selectedPaymentFile.can_regenerate && (
                                                  <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Include</th>
                                                )}
                                                {role === 'STORE_MANAGER' && !(selectedPaymentFile.payment_status === 'APPROVED' || selectedPaymentFile.payment_status === 'PAID' || selectedPaymentFile.is_payment_file_approved) && (
                                                  <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Reject</th>
                                                )}
                                                {role === 'AP_TEAM' && !selectedPaymentFile.is_ap_approved && !selectedPaymentFile.is_ap_rejected && (
                                                  <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>AP Reject</th>
                                                )}
                                                <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Invoice</th>
                                                <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>GST</th>
                                                <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Supplier</th>
                                                <th style={{ padding: '12px', textAlign: 'right', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Amount</th>
                                                <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Review Status</th>
                                                <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>Reason</th>
                                                {role === 'AP_TEAM' && <th style={{ padding: '12px', textAlign: 'left', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>AP Rejection Comment</th>}
                                              </tr>
                                            </thead>
                                            <tbody>
                                              {(selectedPaymentFile.rows || []).map((row, index) => {
                                                const reviewMeta = getPaymentRowReviewMeta(row);
                                                const isChecked = reviewRejectedIds.includes(row.id);
                                                const isPaymentFileLocked = selectedPaymentFile.payment_status === 'APPROVED' || selectedPaymentFile.payment_status === 'PAID' || selectedPaymentFile.is_payment_file_approved;
                                                return (
                                                  <tr key={row.id || `${row.invoice_no}-${index}`} style={{ borderBottom: '1px solid var(--card-border)', backgroundColor: isChecked ? 'rgba(255, 77, 79, 0.08)' : (index % 2 === 0 ? 'transparent' : 'rgba(0,0,0,0.02)') }}>
                                                    {selectedPaymentFile.can_regenerate && (
                                                      <td style={{ padding: '12px' }}>
                                                        <input type="checkbox" checked={regenerationInvoiceIds.includes(row.id)} onChange={() => toggleRegenerationInvoice(row.id)} />
                                                      </td>
                                                    )}
                                                    {role === 'STORE_MANAGER' && !isPaymentFileLocked && (
                                                      <td style={{ padding: '12px' }}>
                                                        <input
                                                          type="checkbox"
                                                          checked={isChecked}
                                                          onChange={() => toggleReviewReject(row.id)}
                                                        />
                                                      </td>
                                                    )}
                                                    {role === 'AP_TEAM' && !selectedPaymentFile.is_ap_approved && !selectedPaymentFile.is_ap_rejected && (
                                                      <td style={{ padding: '12px' }}>
                                                        <input
                                                          type="checkbox"
                                                          checked={isChecked}
                                                          onChange={() => toggleReviewReject(row.id)}
                                                          aria-label={`Reject invoice ${row.invoice_no || row.id} by AP Team`}
                                                        />
                                                      </td>
                                                    )}
                                                    <td style={{ padding: '12px' }}>{row.invoice_no || '—'}</td>
                                                    <td style={{ padding: '12px' }}>{row.gst_number || '—'}</td>
                                                    <td style={{ padding: '12px' }}>{row.supplier_name || '—'}</td>
                                                    <td style={{ padding: '12px', textAlign: 'right', fontFamily: 'monospace' }}>{getPaymentFileRowAmountDisplay(row)}</td>
                                                    <td style={{ padding: '12px' }}>
                                                      <span style={{ color: isChecked ? 'var(--danger)' : reviewMeta.color, fontWeight: '700' }}>
                                                        {row.is_ap_rejected ? 'AP Rejected' : row.is_ap_approved ? 'AP Approved' : isChecked ? 'Marked Rejected' : reviewMeta.label}
                                                      </span>
                                                    </td>
                                                    <td style={{ padding: '12px', color: 'var(--text-secondary)' }}>{row.ap_rejection_reason || row.review_reason || row.manager_rejection_reason || '—'}</td>
                                                    {role === 'AP_TEAM' && (
                                                      <td style={{ padding: '12px' }}>
                                                        <input type="text" disabled={!isChecked || selectedPaymentFile.is_ap_approved || selectedPaymentFile.is_ap_rejected} value={apRejectedComments[row.id] || ''} onChange={(event) => setApRejectedComments((current) => ({ ...current, [row.id]: event.target.value }))} placeholder={isChecked ? 'Required rejection comment' : 'Select AP Reject first'} style={{ minWidth: '240px', padding: '8px', borderRadius: '8px', border: '1px solid var(--card-border)', backgroundColor: 'var(--background-secondary)', color: 'var(--text-primary)', opacity: isChecked ? 1 : 0.6 }} />
                                                      </td>
                                                    )}
                                                  </tr>
                                                );
                                              })}
                                            </tbody>
                                          </table>
                                        </div>
                                      </div>
                                    </div>

                                    {/* Manager review */}
                                    {role === 'STORE_MANAGER' && !(selectedPaymentFile.payment_status === 'APPROVED' || selectedPaymentFile.payment_status === 'PAID' || selectedPaymentFile.is_payment_file_approved) && (
                                      <div style={{ borderTop: '1px solid var(--card-border)', paddingTop: '1rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                                        <div style={{ fontWeight: '600', color: 'var(--text-primary)' }}>Manager Review</div>
                                        <div style={{ fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                                          Reject invoice rows line-item wise using the checkboxes above, then submit the review.
                                        </div>
                                        <textarea
                                          value={reviewReason}
                                          onChange={(e) => setReviewReason(e.target.value)}
                                          rows={3}
                                          placeholder="Optional rejection reason or notes"
                                          style={{ width: '100%', padding: '10px', borderRadius: '8px', border: '1px solid var(--card-border)', backgroundColor: 'var(--background-secondary)', color: 'var(--text-primary)', boxSizing: 'border-box' }}
                                        />
                                        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                                          <button
                                            onClick={() => submitPaymentFileReview(selectedPaymentFile.id)}
                                            disabled={isSubmittingReview}
                                            style={{ padding: '10px 16px', borderRadius: '10px', border: 'none', backgroundColor: 'var(--primary-accent)', color: '#fff', cursor: 'pointer' }}
                                          >
                                            {isSubmittingReview ? 'Submitting...' : 'Submit Review'}
                                          </button>
                                        </div>
                                      </div>
                                    )}
                                    {role === 'AP_TEAM' && selectedPaymentFile.payment_status === 'APPROVED' && !selectedPaymentFile.is_ap_approved && (
                                      <div style={{ borderTop: '1px solid var(--card-border)', paddingTop: '1rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                                        <button onClick={() => submitApReview('approve')} disabled={isSubmittingReview} style={{ padding: '10px 16px', borderRadius: '10px', border: 'none', backgroundColor: 'var(--success)', color: '#fff', cursor: 'pointer', opacity: isSubmittingReview ? 0.6 : 1 }}>
                                          {isSubmittingReview ? 'Submitting...' : 'Approve Payment File'}
                                        </button>
                                        <button onClick={() => submitApReview('reject')} disabled={isSubmittingReview} style={{ padding: '10px 16px', borderRadius: '10px', border: 'none', backgroundColor: 'var(--danger)', color: '#fff', cursor: 'pointer', opacity: isSubmittingReview ? 0.6 : 1 }}>
                                          {isSubmittingReview ? 'Submitting...' : 'Submit AP Rejections'}
                                        </button>
                                      </div>
                                    )}
                                </>
                            ) : (
                                <div style={{ color: 'var(--text-secondary)' }}>Select a payment file from the list to see its details.</div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </div>
      )}

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
                          <button
                              onClick={() => {
                                  if (isEditingDoc) setEditDocData(selectedDocument.parsed_data || {});
                                  setIsEditingDoc(!isEditingDoc);
                              }}
                              style={{ padding: '8px 16px', backgroundColor: isEditingDoc ? 'var(--background-secondary)' : 'var(--primary-accent)', color: isEditingDoc ? 'var(--text-primary)' : 'white', border: isEditingDoc ? '1px solid var(--card-border)' : 'none' }}
                          >
                              {isEditingDoc ? 'Cancel Editing' : 'Manual Correction'}
                          </button>
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
                                          <div style={{ padding: '1rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '10px 12px' }}>
                                                  {DOCUMENT_DETAIL_FIELDS.map(({ key, label, inputType = 'text', step }) => (
                                                      <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                                                          <label htmlFor={`manual-${key}`} style={{ fontSize: '0.8rem', fontWeight: '600', color: 'var(--text-secondary)' }}>{label}</label>
                                                          <input
                                                              id={`manual-${key}`}
                                                              type={inputType}
                                                              step={step}
                                                              name={key}
                                                              value={editDocData[key] ?? ''}
                                                              onChange={handleEditDocChange}
                                                              style={{ height: '34px', boxSizing: 'border-box', padding: '6px 8px', borderRadius: '4px', border: '1px solid var(--primary-accent)', backgroundColor: 'var(--card-background)', color: 'var(--text-primary)', fontSize: '0.9rem' }}
                                                          />
                                                      </div>
                                                  ))}
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

      {/* Full-screen payment file preview modal */}
      {isPaymentFilePreviewModalOpen && (
        <div style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            backgroundColor: 'rgba(0, 0, 0, 0.65)',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            zIndex: 10003,
            padding: '1rem'
        }}>
            <div style={{
                width: '95%',
                maxWidth: '1600px',
                maxHeight: '95vh',
                overflowY: 'auto',
                backgroundColor: 'var(--card-background)',
                borderRadius: '16px',
                boxShadow: '0 18px 50px rgba(0,0,0,0.35)',
                border: '1px solid var(--card-border)',
                padding: '24px',
                position: 'relative'
            }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', marginBottom: '1.5rem' }}>
                    <div>
                        <h2 style={{ margin: 0, color: 'var(--text-primary)' }}>
                          Payment File Preview
                        </h2>
                        <p style={{ margin: '8px 0 0', color: 'var(--text-secondary)', fontSize: '0.95rem' }}>
                          {previewPaymentFile ? `ID: ${previewPaymentFile.id} | Type: ${previewPaymentFile.payment_type}` : 'Loading...'}
                        </p>
                    </div>
                    <button
                      onClick={closePaymentFilePreviewModal}
                      style={{
                          border: 'none',
                          background: 'transparent',
                          color: 'var(--text-secondary)',
                          fontSize: '1.75rem',
                          cursor: 'pointer'
                      }}
                      aria-label="Close payment file preview"
                    >
                      ×
                    </button>
                </div>

                {isFetchingPreviewPaymentFile ? (
                  <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                    Loading payment file preview...
                  </div>
                ) : previewPaymentFile ? (
                  <>
                    <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                      {previewPaymentFile.download_url && (
                        <a href={getFormattedDownloadUrl(previewPaymentFile.download_url, 'xlsx')} target="_blank" rel="noreferrer" style={{ color: 'var(--primary-accent)', fontWeight: '600', display: 'inline-block', padding: '10px 16px', borderRadius: '10px', backgroundColor: 'var(--background-secondary)', border: '1px solid var(--card-border)' }}>
                          Download Excel
                        </a>
                      )}
                      {previewPaymentFile.download_url && (
                        <a href={getFormattedDownloadUrl(previewPaymentFile.download_url, 'csv')} target="_blank" rel="noreferrer" style={{ color: 'var(--primary-accent)', fontWeight: '600', display: 'inline-block', padding: '10px 16px', borderRadius: '10px', backgroundColor: 'var(--background-secondary)', border: '1px solid var(--card-border)' }}>
                          Download CSV
                        </a>
                      )}
                    </div>
                    <div style={{ overflowX: 'auto' }}>
                      {(() => {
                        const isICICI = previewPaymentFile.payment_type === 'ICICI';
                        const today = new Date();
                        const dateStr = `${String(today.getDate()).padStart(2,'0')}-${String(today.getMonth()+1).padStart(2,'0')}-${today.getFullYear()}`;
                        const cols = isICICI ? [
                          { label: 'PYMT_PROD_TYPE_CODE', get: () => 'PAB_VENDOR' },
                          { label: 'PYMT_MODE',           get: () => 'NEFT' },
                          { label: 'DEBIT_ACC_NO',        get: () => '' },
                          { label: 'BNF_NAME',            get: row => row.bnf_name || row.supplier_name || '—' },
                          { label: 'BENE_ACC_NO',         get: row => row.account_number || '—' },
                          { label: 'BENE_IFSC',           get: row => row.ifsc_code || '—' },
                          { label: 'AMOUNT',              get: row => { const n = parseFloat(row.amount); return Number.isFinite(n) ? n.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—'; }, align: 'right' },
                          { label: 'DEBIT_NARR',          get: () => '' },
                          { label: 'CREDIT_NARR',         get: () => '' },
                          { label: 'MOBILE_NUM',          get: row => row.phone || '—' },
                          { label: 'EMAIL_ID',            get: row => row.email || '—' },
                          { label: 'REMARK',              get: row => row.remarks || '' },
                          { label: 'PYMT_DATE',           get: () => dateStr },
                          { label: 'REF_NO',              get: row => row.payment_reference_number || '' },
                          { label: 'ADDL_INFO1',          get: row => row.gst_number || '—' },
                          { label: 'ADDL_INFO2',          get: () => '' },
                          { label: 'ADDL_INFO3',          get: () => '' },
                          { label: 'ADDL_INFO4',          get: () => '' },
                          { label: 'ADDL_INFO5',          get: () => '' },
                        ] : [
                          { label: 'TYPE',                            get: () => 'NEFT' },
                          { label: 'AMT',                             get: row => { const n = parseFloat(row.amount); return Number.isFinite(n) ? n.toFixed(2) : '—'; }, align: 'right' },
                          { label: 'DATE',                            get: () => dateStr },
                          { label: 'DEBIT ACCOUNT NUMBER',            get: () => '' },
                          { label: 'BEN.NAME',                        get: row => row.supplier_name || '—' },
                          { label: 'PHONE NUMB',                      get: row => row.phone || '—' },
                          { label: 'BEN.ACCOU',                       get: row => row.account_number || '—' },
                          { label: 'IFSC CODE',                       get: row => row.ifsc_code || '—' },
                          { label: 'PAYMENT INSTRCUCTION',            get: () => 'VENDOR PAYMENT' },
                          { label: 'COR.REF NO (UNIQUE) PV NUMBER',   get: row => row.payment_reference_number || '' },
                          { label: 'PAYABLE CURRENCY',                get: () => 'INR' },
                          { label: 'BENEFICIARY ADDRESS',             get: row => row.address || '—' },
                          { label: 'EMAIL',                           get: row => row.email || '—' },
                          { label: 'BENEFICIARY ADVISE DISPATCH',     get: () => 'E' },
                        ];

                        return (
                          <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '2200px', fontSize: '0.82rem' }}>
                            <thead style={{ backgroundColor: 'var(--background-secondary)', position: 'sticky', top: 0, zIndex: 1 }}>
                              <tr>
                                {cols.map(col => (
                                  <th key={col.label} style={{ padding: '10px 12px', textAlign: col.align || 'left', fontWeight: '600', color: 'var(--text-primary)', borderBottom: '2px solid var(--card-border)', whiteSpace: 'nowrap' }}>
                                    {col.label}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {(previewPaymentFile.rows || []).map((row, index) => (
                                <tr key={row.id || index} style={{
                                  borderBottom: '1px solid var(--card-border)',
                                  backgroundColor: index % 2 === 0 ? 'transparent' : 'rgba(0,0,0,0.02)'
                                }}>
                                  {cols.map(col => (
                                    <td key={col.label} style={{ padding: '10px 12px', textAlign: col.align || 'left', whiteSpace: 'nowrap' }}>
                                      {col.get(row)}
                                    </td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        );
                      })()}
                    </div>
                  </>
                ) : (
                  <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-secondary)' }}>
                    Unable to load payment file preview.
                  </div>
                )}
            </div>
        </div>
      )}

    </div>
  );
};

export default Dashboard;
