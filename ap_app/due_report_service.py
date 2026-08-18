import re


GSTIN_PATTERN = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b", re.IGNORECASE)


def extract_gst_from_supplier_name(supplier_name):
    """Extract an embedded GSTIN while retaining the cleaned supplier name."""
    if not supplier_name:
        return supplier_name, ""

    supplier_text = str(supplier_name).strip()
    match = GSTIN_PATTERN.search(supplier_text)
    if not match:
        return supplier_text, ""

    gst_number = match.group(0).upper()
    cleaned_name = f"{supplier_text[:match.start()]} {supplier_text[match.end():]}"
    return re.sub(r"\s+", " ", cleaned_name).strip(), gst_number
