/**
 * Advance Deposit Tracker — Google Apps Script
 * Writes form submissions DIRECTLY to Supabase (no backend / ngrok needed).
 *
 * SETUP (one-time):
 *   1. Open Apps Script editor for your Google Form.
 *   2. Paste this entire file.
 *   3. Run setupScriptProperties() ONCE to save credentials.
 *   4. Add a trigger: onFormSubmit → From form → On form submit.
 *   5. Authorize when prompted.
 */

// ─── Step 1: Run this once to store credentials ───────────────────────────────
function setupScriptProperties() {
  var props = PropertiesService.getScriptProperties();
  props.setProperties({
    SUPABASE_URL:         'https://YOUR-PROJECT-REF.supabase.co',
    SUPABASE_SERVICE_KEY: 'PASTE_SUPABASE_SERVICE_ROLE_KEY_HERE'  // fill in, run once, then clear
  });
  Logger.log('Script properties saved.');
}

// ─── Step 2: This fires on every form submission ───────────────────────────────
function onFormSubmit(e) {
  try {
    var props     = PropertiesService.getScriptProperties();
    var BASE_URL  = props.getProperty('SUPABASE_URL');
    var API_KEY   = props.getProperty('SUPABASE_SERVICE_KEY');

    if (!BASE_URL || !API_KEY) {
      throw new Error('Run setupScriptProperties() first.');
    }

    // ── Parse form responses ──────────────────────────────────────────────────
    var responses = e.response.getItemResponses();
    var data = {};
    for (var i = 0; i < responses.length; i++) {
      var title  = responses[i].getItem().getTitle().trim();
      var answer = responses[i].getResponse();
      data[title] = answer ? answer.toString().trim() : '';
    }

    Logger.log('Form data: ' + JSON.stringify(data));

    // Field mapping — try multiple title variants to handle spacing differences
    var FIELD = {
      sunshine_invoice:  data['Sunshine Invoice Number'] || '',
      vertical_name:     data['Vertical/Category'] || data['Vertical/ Category'] || data['Vertical / Category'] || '',
      customer_name:     data['Select Customer']         || '',
      supplier_name:     data['Select Supplier']         || '',
      supplier_invoice:  data['Supplier Invoice Number'] || '',
      total_amount:      data['Total Supplier Proforma Invoice Amount'] || '0',
      deposit_pct:       data['Deposit Advance (%)'] || data['Deposit Advance  (%)'] || data['Deposit Advance Percentage'] || '0',
      currency:          data['Currency of Advance Deposit'] || 'USD',
      ship_date:         data['Estimated Shipment Date'] || '',
      remarks:           data['Remarks']                 || null,
    };

    // Respondent email (who submitted the form)
    var respondentEmail = e.response.getRespondentEmail();
    Logger.log('Respondent: ' + respondentEmail);

    // ── Deduplicate: check if this response_id was already processed ──────────
    var responseId = e.response.getId();
    var existing = supabaseGet(BASE_URL, API_KEY,
      'google_form_submissions?google_response_id=eq.' + encodeURIComponent(responseId) + '&select=id');
    if (existing && existing.length > 0) {
      Logger.log('Duplicate submission ignored: ' + responseId);
      return;
    }

    // ── Look up UUIDs ─────────────────────────────────────────────────────────
    var supplierId  = lookupId(BASE_URL, API_KEY, 'suppliers',  'name', FIELD.supplier_name);
    var customerId  = lookupId(BASE_URL, API_KEY, 'customers',  'name', FIELD.customer_name);
    var verticalId  = lookupVertical(BASE_URL, API_KEY, FIELD.vertical_name);
    var createdById = lookupId(BASE_URL, API_KEY, 'users',      'email', respondentEmail);

    if (!supplierId)  throw new Error('Supplier not found: ' + FIELD.supplier_name);
    if (!customerId)  throw new Error('Customer not found: ' + FIELD.customer_name);
    if (!verticalId)  throw new Error('Vertical not found: ' + FIELD.vertical_name);
    if (!createdById) throw new Error('User not found for email: ' + respondentEmail);

    // ── Calculate deposit amount ──────────────────────────────────────────────
    var totalAmt   = parseFloat(FIELD.total_amount.replace(/,/g, '')) || 0;
    var depositPct = parseFloat(FIELD.deposit_pct.replace('%', ''))   || 0;
    var depositAmt = Math.round(totalAmt * depositPct / 100 * 100) / 100;

    // ── Normalise currency (RMB → CNY) ────────────────────────────────────────
    var currency = FIELD.currency.split(' ')[0].toUpperCase();
    if (currency === 'RMB') currency = 'CNY';
    var validCurrencies = ['USD', 'EUR', 'CNY', 'GBP', 'AED', 'INR', 'OTHER'];
    if (validCurrencies.indexOf(currency) === -1) currency = 'USD';

    // ── Generate request number (ADT-YYYY-NNNNN) ─────────────────────────────
    var requestNumber = generateRequestNumber(BASE_URL, API_KEY);

    // ── Parse shipment date (handles DD/MM/YYYY and YYYY-MM-DD) ──────────────
    var shipDate = parseDate(FIELD.ship_date);

    // ── Insert deposit_request ────────────────────────────────────────────────
    var requestPayload = {
      request_number:              requestNumber,
      supplier_id:                 supplierId,
      customer_id:                 customerId,
      vertical_id:                 verticalId,
      created_by:                  createdById,
      sunshine_invoice_number:     FIELD.sunshine_invoice || null,
      supplier_invoice_number:     FIELD.supplier_invoice || null,
      currency:                    currency,
      deposit_amount:              depositAmt.toFixed(2),
      deposit_percentage:          depositPct.toFixed(2),
      total_supplier_invoice_amount: totalAmt.toFixed(2),
      estimated_shipment_date:     shipDate,
      remarks:                     FIELD.remarks || null,
      submission_source:           'google_form',
      current_status:              'pending_payment',
      is_locked:                   false,
      is_deleted:                  false
    };

    var insertedRequest = supabasePost(BASE_URL, API_KEY, 'deposit_requests', requestPayload);
    if (!insertedRequest || !insertedRequest[0]) {
      throw new Error('Failed to insert deposit_request');
    }
    var depositRequestId = insertedRequest[0].id;
    Logger.log('Created deposit request: ' + depositRequestId + ' (' + requestNumber + ')');

    // ── Record form submission for deduplication ──────────────────────────────
    supabasePost(BASE_URL, API_KEY, 'google_form_submissions', {
      deposit_request_id:   depositRequestId,
      google_response_id:   responseId,
      submitted_by_email:   respondentEmail,
      submitted_at:         new Date().toISOString(),
      raw_payload_json:     data,
      processed:            true
    });

    Logger.log('SUCCESS: ' + requestNumber + ' created for ' + FIELD.supplier_name);

  } catch (err) {
    Logger.log('ERROR in onFormSubmit: ' + err.message);
    // Rethrow so the execution log shows it as failed
    throw err;
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function lookupId(baseUrl, apiKey, table, column, value) {
  if (!value) return null;
  var encoded = encodeURIComponent(value);
  var rows = supabaseGet(baseUrl, apiKey,
    table + '?' + column + '=eq.' + encoded + '&select=id&limit=1');
  return (rows && rows.length > 0) ? rows[0].id : null;
}

/** Vertical lookup: tries exact match first, then strips leading number+dot prefix. */
function lookupVertical(baseUrl, apiKey, rawName) {
  // Try exact match e.g. "Frozen" or "08.Frozen"
  var id = lookupId(baseUrl, apiKey, 'verticals', 'name', rawName);
  if (id) return id;

  // Strip "08." prefix if present: "08.Frozen" → "Frozen"
  var stripped = rawName.replace(/^\d+\.\s*/, '').trim();
  if (stripped !== rawName) {
    id = lookupId(baseUrl, apiKey, 'verticals', 'name', stripped);
    if (id) return id;
  }

  // Case-insensitive partial match via ilike
  var rows = supabaseGet(baseUrl, apiKey,
    'verticals?name=ilike.*' + encodeURIComponent(stripped) + '*&select=id&limit=1');
  return (rows && rows.length > 0) ? rows[0].id : null;
}

/** Generate next ADT-YYYY-NNNNN number by counting existing requests this year. */
function generateRequestNumber(baseUrl, apiKey) {
  var year   = new Date().getFullYear();
  var prefix = 'ADT-' + year + '-';
  var rows   = supabaseGet(baseUrl, apiKey,
    'deposit_requests?request_number=like.' + encodeURIComponent(prefix + '*') + '&select=id');
  var count  = rows ? rows.length : 0;
  return prefix + String(count + 1).padStart(5, '0');
}

/** Parse date string in DD/MM/YYYY or YYYY-MM-DD or MM/DD/YYYY formats. */
function parseDate(value) {
  if (!value) return null;
  value = value.trim();

  // YYYY-MM-DD
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value;

  // DD/MM/YYYY
  var dmy = value.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (dmy) return dmy[3] + '-' + dmy[2].padStart(2,'0') + '-' + dmy[1].padStart(2,'0');

  // MM/DD/YYYY (US format — less common)
  var mdy = value.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (mdy) return mdy[3] + '-' + mdy[1].padStart(2,'0') + '-' + mdy[2].padStart(2,'0');

  return value; // return as-is, let Supabase validate
}

// ─── Supabase REST API wrappers ───────────────────────────────────────────────

function supabaseGet(baseUrl, apiKey, path) {
  var url = baseUrl + '/rest/v1/' + path;
  var resp = UrlFetchApp.fetch(url, {
    method: 'GET',
    headers: {
      'apikey':        apiKey,
      'Authorization': 'Bearer ' + apiKey,
      'Content-Type':  'application/json'
    },
    muteHttpExceptions: true
  });
  var code = resp.getResponseCode();
  var body = resp.getContentText();
  if (code !== 200) {
    Logger.log('GET ' + path + ' → ' + code + ': ' + body);
    return null;
  }
  return JSON.parse(body);
}

function supabasePost(baseUrl, apiKey, table, payload) {
  var url = baseUrl + '/rest/v1/' + table;
  var resp = UrlFetchApp.fetch(url, {
    method: 'POST',
    headers: {
      'apikey':        apiKey,
      'Authorization': 'Bearer ' + apiKey,
      'Content-Type':  'application/json',
      'Prefer':        'return=representation'
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
  var code = resp.getResponseCode();
  var body = resp.getContentText();
  Logger.log('POST ' + table + ' → ' + code + ': ' + body);
  if (code < 200 || code >= 300) {
    throw new Error('Supabase POST failed (' + code + '): ' + body);
  }
  return JSON.parse(body);
}
