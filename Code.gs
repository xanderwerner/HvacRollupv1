/**
 * CRM SYNC BRIDGE — Acquisition Call Tracker
 * Lets Claude (or anyone with the secret token) push data into this sheet.
 *
 * SETUP (one time, ~3 minutes):
 * 1. Open the Google Sheet -> Extensions -> Apps Script
 * 2. Delete any code in the editor, paste this entire file, click Save (disk icon)
 * 3. Click Deploy -> New deployment -> gear icon -> Web app
 *    - Description: CRM sync
 *    - Execute as: Me
 *    - Who has access: Anyone
 * 4. Click Deploy, authorize when asked, and COPY THE WEB APP URL (ends in /exec)
 * 5. Paste that URL back to Claude in the chat
 *
 * SECURITY: anyone who has BOTH the URL and the token below can write to this
 * sheet. Keep them private. To revoke access at any time: Deploy -> Manage
 * deployments -> Archive, or just change the TOKEN string and redeploy.
 */

var TOKEN = "c2574063e581881f6cc04b4cde2a54b7";

// Companies tab: columns O-R (15-18) are formulas and are always restored after import
var CO_SHEET = "Companies";
var CO_COLS = 27; // A..AA
var CALL_SHEET = "Call Log";
var CALL_COLS = 10; // A..J
var IMPORT_PREFIX_COMPANIES = "crm_companies_import"; // Drive filename prefix
var IMPORT_PREFIX_CALLS = "crm_calllog_import";

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu("CRM Sync")
    .addItem("Import Companies from Drive file", "menuImportCompanies")
    .addItem("Append Call Log rows from Drive file", "menuImportCalls")
    .addToUi();
}

function menuImportCompanies() {
  var n = importCompanies();
  SpreadsheetApp.getUi().alert("Imported " + n + " companies (formulas restored).");
}

function menuImportCalls() {
  var n = importCalls();
  SpreadsheetApp.getUi().alert("Appended " + n + " call log rows.");
}

function doGet(e) {
  var p = (e && e.parameter) || {};
  if (p.token !== TOKEN) {
    return ContentService.createTextOutput(JSON.stringify({ok: false, error: "bad token"}))
      .setMimeType(ContentService.MimeType.JSON);
  }
  var out = {ok: true, action: p.action || "ping"};
  try {
    if (p.action === "import_companies") out.rows = importCompanies();
    else if (p.action === "import_calls") out.rows = importCalls();
    else if (p.action === "ping") out.msg = "bridge alive";
    else if (p.action) { out.ok = false; out.error = "unknown action"; }
  } catch (err) {
    out.ok = false; out.error = String(err);
  }
  return ContentService.createTextOutput(JSON.stringify(out))
    .setMimeType(ContentService.MimeType.JSON);
}

function newestFile(prefix) {
  var it = DriveApp.searchFiles(
    "title contains '" + prefix + "' and trashed = false");
  var best = null;
  while (it.hasNext()) {
    var f = it.next();
    if (!best || f.getLastUpdated() > best.getLastUpdated()) best = f;
  }
  if (!best) throw "No Drive file found with prefix: " + prefix;
  return best;
}

function readCsv(prefix) {
  var f = newestFile(prefix);
  var rows = Utilities.parseCsv(f.getBlob().getDataAsString("UTF-8"));
  if (rows.length < 2) throw "Import file has no data rows";
  return rows.slice(1); // drop header
}

/** Replace all Companies data rows; restore auto-formula columns O-R. */
function importCompanies() {
  var data = readCsv(IMPORT_PREFIX_COMPANIES);
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(CO_SHEET);
  if (!sh) throw "Sheet not found: " + CO_SHEET;
  var maxRows = Math.max(sh.getMaxRows() - 1, data.length);
  sh.getRange(2, 1, maxRows, CO_COLS).clearContent();
  // pad/trim every row to 27 cols, blank out O-R (idx 14-17) — formulas go there
  var vals = data.map(function (r) {
    var row = r.slice(0, CO_COLS);
    while (row.length < CO_COLS) row.push("");
    row[14] = ""; row[15] = ""; row[16] = ""; row[17] = "";
    return row;
  });
  sh.getRange(2, 1, vals.length, CO_COLS).setValues(vals);
  // restore formulas in O-R for every data row
  var f = [];
  for (var i = 0; i < vals.length; i++) {
    var r = i + 2;
    f.push([
      '=IF(B' + r + '="","",IFERROR(LOOKUP(2,1/(\'Call Log\'!$C$2:$C$5000=B' + r + '),\'Call Log\'!$B$2:$B$5000),""))',
      '=IF(B' + r + '="","",COUNTIFS(\'Call Log\'!$C$2:$C$5000,B' + r + ',\'Call Log\'!$A$2:$A$5000,">="&(TODAY()-WEEKDAY(TODAY(),2)+1)))',
      '=IF(B' + r + '="","",COUNTIF(\'Call Log\'!$C$2:$C$5000,B' + r + '))',
      '=IF(B' + r + '="","",IFERROR(IF(MAXIFS(\'Call Log\'!$A$2:$A$5000,\'Call Log\'!$C$2:$C$5000,B' + r + ')=0,"",MAXIFS(\'Call Log\'!$A$2:$A$5000,\'Call Log\'!$C$2:$C$5000,B' + r + ')),""))'
    ]);
  }
  sh.getRange(2, 15, f.length, 4).setFormulas(f);
  return vals.length;
}

/** Append rows to the Call Log (never overwrites existing calls). */
function importCalls() {
  var data = readCsv(IMPORT_PREFIX_CALLS);
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(CALL_SHEET);
  if (!sh) throw "Sheet not found: " + CALL_SHEET;
  var last = sh.getRange(1, 1, sh.getMaxRows(), 1).getValues()
    .reduce(function (acc, v, i) { return v[0] !== "" ? i + 1 : acc; }, 1);
  var vals = data.map(function (r) {
    var row = r.slice(0, CALL_COLS);
    while (row.length < CALL_COLS) row.push("");
    return row;
  });
  sh.getRange(last + 1, 1, vals.length, CALL_COLS).setValues(vals);
  return vals.length;
}
