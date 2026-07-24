/**
 * Advance Deposit Tracker — Google Apps Script
 * Attach this to your Google Form via Extensions → Apps Script.
 *
 * Setup:
 *  1. Open the Script editor for your Google Form.
 *  2. Paste this file in its entirety.
 *  3. Set WEBHOOK_URL and SECRET_KEY in Script Properties
 *     (Project Settings → Script Properties):
 *       WEBHOOK_URL = https://your-api.onrender.com/api/v1/webhooks/google-form
 *       SECRET_KEY  = (same value as GOOGLE_WEBHOOK_SECRET in FastAPI .env)
 *  4. Add a trigger: Triggers → Add Trigger → onFormSubmit → From form → On form submit.
 *  5. Authorize the script (requires your Google account).
 */

// ---------------------------------------------------------------------------
// Configuration — read from Script Properties (never hardcode secrets)
// ---------------------------------------------------------------------------
function getConfig_() {
  var props = PropertiesService.getScriptProperties();
  return {
    webhookUrl: props.getProperty('WEBHOOK_URL'),
    secretKey:  props.getProperty('SECRET_KEY'),
  };
}

// ---------------------------------------------------------------------------
// Main trigger — called automatically on every form submission
// ---------------------------------------------------------------------------
function onFormSubmit(e) {
  try {
    var config = getConfig_();
    if (!config.webhookUrl || !config.secretKey) {
      Logger.log('ERROR: WEBHOOK_URL or SECRET_KEY not set in Script Properties.');
      return;
    }

    var payload = buildPayload_(e);
    var payloadJson = JSON.stringify(payload);
    var signature = computeHmacSha256_(payloadJson, config.secretKey);

    var options = {
      method: 'post',
      contentType: 'application/json',
      headers: {
        'X-Signature': signature,
        'X-Source': 'google-form',
      },
      payload: payloadJson,
      muteHttpExceptions: true,
    };

    var response = UrlFetchApp.fetch(config.webhookUrl, options);
    var code = response.getResponseCode();

    if (code === 200 || code === 201) {
      Logger.log('SUCCESS: response ' + code + ' for response_id=' + payload.response_id);
    } else {
      var body = response.getContentText();
      Logger.log('WARN: HTTP ' + code + ' — ' + body);
      // Store for retry job
      storeFailedSubmission_(payload, code, body);
    }
  } catch (err) {
    Logger.log('ERROR in onFormSubmit: ' + err.toString());
    storeFailedSubmission_(buildPayload_(e), 0, err.toString());
  }
}

// ---------------------------------------------------------------------------
// Retry trigger — attach to a time-based trigger every 5 minutes
// ---------------------------------------------------------------------------
function retryFailedSubmissions() {
  var store = PropertiesService.getScriptProperties();
  var failedRaw = store.getProperty('FAILED_SUBMISSIONS');
  if (!failedRaw) return;

  var failed = JSON.parse(failedRaw);
  var remaining = [];
  var config = getConfig_();

  for (var i = 0; i < failed.length; i++) {
    var item = failed[i];
    if (item.retries >= 3) {
      Logger.log('DROPPED after 3 retries: ' + item.payload.response_id);
      continue;
    }

    var payloadJson = JSON.stringify(item.payload);
    var signature = computeHmacSha256_(payloadJson, config.secretKey);
    var options = {
      method: 'post',
      contentType: 'application/json',
      headers: { 'X-Signature': signature, 'X-Source': 'google-form-retry' },
      payload: payloadJson,
      muteHttpExceptions: true,
    };

    try {
      var response = UrlFetchApp.fetch(config.webhookUrl, options);
      var code = response.getResponseCode();
      if (code === 200 || code === 201 || code === 409) {
        // 409 = duplicate already processed — consider it done
        Logger.log('RETRY SUCCESS: ' + item.payload.response_id);
      } else {
        item.retries += 1;
        remaining.push(item);
      }
    } catch (err) {
      item.retries += 1;
      remaining.push(item);
    }
  }

  if (remaining.length > 0) {
    store.setProperty('FAILED_SUBMISSIONS', JSON.stringify(remaining));
  } else {
    store.deleteProperty('FAILED_SUBMISSIONS');
  }
}

// ---------------------------------------------------------------------------
// Build the payload object from the form submit event
// ---------------------------------------------------------------------------
function buildPayload_(e) {
  var response = e.response;
  var items = response.getItemResponses().map(function(r) {
    return {
      question: r.getItem().getTitle(),
      answer:   r.getResponse(),
    };
  });

  return {
    response_id:      response.getId(),
    submitted_at:     response.getTimestamp().toISOString(),
    respondent_email: response.getRespondentEmail() || null,
    items:            items,
  };
}

// ---------------------------------------------------------------------------
// Store failed submission for retry
// ---------------------------------------------------------------------------
function storeFailedSubmission_(payload, httpCode, errorMsg) {
  var store = PropertiesService.getScriptProperties();
  var existingRaw = store.getProperty('FAILED_SUBMISSIONS');
  var existing = existingRaw ? JSON.parse(existingRaw) : [];
  existing.push({ payload: payload, retries: 0, lastError: errorMsg, httpCode: httpCode });
  store.setProperty('FAILED_SUBMISSIONS', JSON.stringify(existing));
}

// ---------------------------------------------------------------------------
// HMAC-SHA256 using Google's Utilities.computeHmacSha256Signature
// Returns hex string matching Python's hmac.new(..., digestmod=sha256).hexdigest()
// ---------------------------------------------------------------------------
function computeHmacSha256_(message, secret) {
  var rawBytes = Utilities.computeHmacSha256Signature(message, secret);
  return rawBytes.map(function(b) {
    return ('0' + (b & 0xff).toString(16)).slice(-2);
  }).join('');
}
