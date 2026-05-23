# Fix: harvest.yml YAML syntax error at line 166

**Date:** 2026-05-23  
**File changed:** `.github/workflows/harvest.yml`

## Problem

The workflow was failing with a YAML parse error:

```
yaml.scanner.ScannerError: mapping values are not allowed here
  in "<unicode string>", line 166, column 17:
              if ffs:
                    ^
```

### Root cause

There were two related issues in the `Post GitHub Issue summary` step's `run: |` block:

1. **Lines 156–158 — unindented shell line continuations:**  
   The `REPORT_DATE_UK` command used shell `\` line-continuation characters:
   ```sh
   REPORT_DATE_UK=$(python -c "import json,datetime; ...; v=d.get('target_date','unknown');\
   try: print(datetime.datetime.strptime(v,'%Y-%m-%d').strftime('%d/%m/%Y'))\
   except Exception: print(v)")
   ```
   The continuation lines (`try:` and `except Exception:`) had **zero leading spaces**. In a YAML literal block scalar (`|`), any non-empty line with indentation less than the block's level (10 spaces here) **terminates the block**. So YAML stopped treating the content as a raw string at line 157, and began trying to parse the remaining lines as YAML mappings — eventually hitting the unsupported `if ffs:` colon construct on line 166.

2. **Lines 169–170 and 180 — f-strings with `\"`-escaped quotes:**  
   The FAILED_LIST and HTML_LIST blocks used f-strings with backslash-escaped double quotes (`f\"`), e.g.:
   ```python
   lines.append(f\"- **{f['display_name']}** ({f.get('url','')})  \")
   ```
   This is invalid in Python < 3.12 (backslash inside f-string expressions) and causes YAML embedding issues.

## Changes made

### 1. `REPORT_DATE_UK` — replaced multi-line shell continuation with a single-line command

**Before:**
```sh
REPORT_DATE_UK=$(python -c "import json,datetime; d=json.load(open('Bulletins/report.json')); v=d.get('target_date','unknown');\
try: print(datetime.datetime.strptime(v,'%Y-%m-%d').strftime('%d/%m/%Y'))\
except Exception: print(v)")
```

**After:**
```sh
REPORT_DATE_UK=$(python -c "import json; d=json.load(open('Bulletins/report.json')); v=d.get('target_date','unknown'); parts=v.split('-'); print('/'.join([parts[2],parts[1],parts[0]]) if len(parts)==3 else v)")
```

This splits the ISO date string `YYYY-MM-DD` on `-` and reverses the parts to produce `DD/MM/YYYY`, falling back to the raw value if the date is not in 3-part format. No `datetime` import needed, no `try/except`, no shell line continuations.

### 2. `FAILED_LIST` — replaced f-strings with string concatenation

**Before:**
```python
lines.append(f\"- **{f['display_name']}** ({f.get('url','')})  \")
lines.append(f\"  _Reason: {f.get('error','unknown')}_\")
```

**After:**
```python
lines.append('- **' + f['display_name'] + '** (' + f.get('url','') + ')  ')
lines.append('  _Reason: ' + f.get('error','unknown') + '_')
```

### 3. `HTML_LIST` — replaced f-string with string concatenation

**Before:**
```python
print('\n'.join(f\"- **{h['display_name']}**: [{h['url']}]({h['url']})\" for h in hls))
```

**After:**
```python
print('\n'.join('- **' + h['display_name'] + '**: [' + h['url'] + '](' + h['url'] + ')' for h in hls))
```

## Verification

After the changes, the YAML parses cleanly:
```
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/harvest.yml').read()); print('YAML valid!')"
# → YAML valid!
```
