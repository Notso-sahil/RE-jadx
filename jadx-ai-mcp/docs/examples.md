# Examples

Real-world examples demonstrating JADX-AI-MCP capabilities.

## Table of Contents

- [Security Analysis](#security-analysis)
- [Reverse Engineering](#reverse-engineering)
- [Debugging](#debugging)
- [Code Refactoring](#code-refactoring)
- [Malware Analysis](#malware-analysis)

---

## Security Analysis

### Example 1: Comprehensive Security Audit

**Goal:** Perform a complete security assessment of an Android APK.

**Prompt:**
```
Perform a comprehensive security audit:

1. Get the AndroidManifest and identify dangerous permissions
2. Get main application classes
3. Search for hardcoded credentials
4. Check for insecure crypto usage
5. Identify WebView security issues
6. Generate a detailed report
```

**Expected Workflow:**

```python
# Step 1: Manifest analysis
manifest = await get_android_manifest()
permissions = manifest['permissions']

dangerous_perms = [p for p in permissions if 'DANGEROUS' in p]
# Found: CAMERA, READ_CONTACTS, ACCESS_FINE_LOCATION

# Step 2: Get app classes
classes = await get_main_application_classes_names()
# 45 classes in com.example.app package

# Step 3: Search for credentials
creds_search = await search_classes_by_keyword("password")
# Found 8 classes with password handling

# Step 4: Crypto analysis
crypto_search = await search_method_by_name("encrypt")
# Found 3 encryption methods

for result in crypto_search['results']:
    source = await get_class_source(result['className'])
    # Analyze crypto implementation

# Step 5: WebView analysis
webview_search = await search_classes_by_keyword("WebView")
# Found 2 WebView implementations

for webview_class in webview_search['results']:
    source = await get_class_source(webview_class['className'])
    # Check for setJavaScriptEnabled, SSL validation, etc.
```

**AI Response:**
```
🔴 CRITICAL FINDINGS:
1. Hardcoded API key in Config.class (line 45)
2. DES encryption used instead of AES (CryptoHelper.java)
3. WebView allows JavaScript without proper validation

🟡 WARNINGS:
1. Over-privileged: CAMERA permission not used
2. Cleartext HTTP traffic allowed
3. SSL certificate validation disabled in NetworkManager

📊 SUMMARY:
- Critical: 3
- High: 5
- Medium: 8
- Low: 12
```

---

### Example 2: Authentication Flow Analysis

**Goal:** Understand and assess the security of the login mechanism.

**Prompt:**
```
Analyze the authentication system:

1. Get the main activity and find login entry point
2. Trace the login method implementation
3. Identify credential storage mechanism
4. Check for password encryption
5. Assess overall security
```

**Workflow:**

```python
# Find login activity
main_activity = await get_main_activity_class()
# com.example.app.SplashActivity

# Search for login methods
login_methods = await search_method_by_name("login")
# Found: LoginActivity.performLogin()

# Get login class source
login_class = await get_class_source("com.example.app.LoginActivity")

# Analyze password handling
password_refs = await get_xrefs_to_field(
    "com.example.app.LoginActivity", 
    "password"
)

# Check credential storage
prefs_search = await search_classes_by_keyword("SharedPreferences")
```

**Finding:**
```
⚠️ SECURITY ISSUE:
The app stores username and password in SharedPreferences 
without encryption.

Location: LoginActivity.java, line 78
Code: prefs.edit().putString("password", plainPassword).apply();

Recommendation: Use Android Keystore or encrypt credentials
```

---

## Reverse Engineering

### Example 3: Deobfuscation Workflow

**Goal:** Systematically deobfuscate an obfuscated APK.

**Prompt:**
```
Help me deobfuscate this app:

1. Identify obfuscation patterns
2. Locate main functionality
3. Rename classes systematically
4. Document findings
```

**Workflow:**

```python
# Get all classes to identify patterns
all_classes = await get_all_classes(offset=0, count=100)
# Pattern identified: single-letter package names (a.b.c, d.e.f)

# Get main app classes (usually less obfuscated)
main_classes = await get_main_application_classes_names()
# com.example.secure

# Get main activity for context
main_activity = await get_main_activity_class()
# com.example.secure.a

# Analyze main activity
activity_source = await get_class_source("com.example.secure.a")
# Contains: onCreate, initializeApp, loadConfig

# Rename based on functionality
await rename_class("com.example.secure.a", "MainActivity")
await rename_method("a()", "initializeApp")
await rename_method("b()", "loadConfig")

# Find and rename helper classes
xrefs = await get_xrefs_to_class("com.example.secure.b")
# Referenced in MainActivity.initializeApp()
# Appears to handle network requests

await rename_class("com.example.secure.b", "NetworkManager")

# Continue pattern for crypto classes
crypto_search = await search_method_by_name("cipher")
# Found in com.example.secure.c

await rename_class("com.example.secure.c", "CryptoHelper")
```

**Result:**
```
✅ DEOBFUSCATION PROGRESS:

Original → Renamed:
com.example.secure.a → MainActivity
com.example.secure.b → NetworkManager  
com.example.secure.c → CryptoHelper
com.example.secure.d → DatabaseHelper
com.example.secure.e → AuthManager

Methods renamed: 47
Fields renamed: 23
```

---

### Example 4: Native Library Analysis

**Goal:** Identify and analyze native (JNI) methods.

**Prompt:**
```
Find and analyze native methods:

1. Search for native method declarations
2. Locate library loading code
3. Identify JNI function mappings
4. Get smali for detailed analysis
```

**Workflow:**

```python
# Search for native keyword
native_search = await search_classes_by_keyword("native ")

# Typical finding: NativeLib class
native_class = await get_class_source("com.example.NativeLib")

# Get methods
methods = await get_methods_of_class("com.example.NativeLib")
# Found: native String decryptString(byte[])
#        native void initialize()

# Get smali for low-level analysis
smali = await get_smali_of_class("com.example.NativeLib")

# Find library loading
loadlib_search = await search_classes_by_keyword("System.loadLibrary")
# Found in NativeLib.<clinit>()
# Loads: libnative-crypto.so
```

**Finding:**
```
📦 NATIVE LIBRARY ANALYSIS:

Library: libnative-crypto.so

JNI Methods:
1. Java_com_example_NativeLib_decryptString
   - Implements custom crypto
   - Takes encrypted byte array
   - Returns decrypted String

2. Java_com_example_NativeLib_initialize  
   - Performs anti-debug checks
   - Validates app signature
   - Initializes crypto keys

Next steps: Analyze .so file with Ghidra/IDA
```

---

## Debugging

### Example 5: Runtime Analysis

**Goal:** Understand runtime behavior during execution.

**Prompt:**
```
I've set a breakpoint at LoginActivity.performLogin(). Help me analyze:

1. Get current stack trace
2. Inspect variables
3. Check thread state
4. Understand execution flow
```

**Workflow:**

```python
# Breakpoint hit at LoginActivity.performLogin()

# Get stack frames
stack = await debug_get_stack_frames()
```

**Output:**
```json
{
  "stackFrames": [
    {
      "index": 0,
      "className": "com.example.LoginActivity",
      "methodName": "performLogin",
      "lineNumber": 145
    },
    {
      "index": 1,
      "className": "com.example.LoginActivity", 
      "methodName": "onClick",
      "lineNumber": 98
    },
    {
      "index": 2,
      "className": "android.view.View",
      "methodName": "performClick",
      "lineNumber": 7000
    }
  ]
}
```

```python
# Get local variables
variables = await debug_get_variables()
```

**Output:**
```json
{
  "locals": [
    {
      "name": "username",
      "type": "String",
      "value": "admin"
    },
    {
      "name": "password",
      "type": "String",
      "value": "password123"
    },
    {
      "name": "rememberMe",
      "type": "boolean",
      "value": "true"
    }
  ],
  "fields": [
    {
      "name": "mAuthManager",
      "type": "AuthManager",
      "value": "com.example.AuthManager@7f8a9b"
    }
  ]
}
```

```python
# Check threads
threads = await debug_get_threads()
```

**Analysis:**
```
🔍 RUNTIME ANALYSIS:

Execution Flow:
User clicked login button → onClick() → performLogin()

Current State:
- Username: "admin" (plain text in memory)
- Password: "password123" (plain text in memory)  
- RememberMe: true

⚠️ SECURITY ISSUE:
Credentials stored as plain Strings in memory during auth process.
Consider using char[] and clearing after use.

Thread State:
- Main thread: SUSPENDED (at breakpoint)
- Background threads: 3 active (AsyncTask, NetworkThread)
```

---

## Code Refactoring

### Example 6: Systematic Package Refactoring

**Goal:** Refactor obfuscated packages to meaningful names.

**Prompt:**
```
Refactor package structure:

1. Identify current package structure
2. Determine purpose of each package
3. Rename to descriptive names
4. Verify all references updated
```

**Workflow:**

```python
# Get current structure
classes = await get_all_classes()

# Group by package
packages = {}
for cls in classes['items']:
    pkg = '.'.join(cls.split('.')[:-1])
    if pkg not in packages:
        packages[pkg] = []
    packages[pkg].append(cls)

# Analysis shows:
# a.b.c - networking code (15 classes)
# a.b.d - crypto code (8 classes)
# a.b.e - database code (12 classes)

# Rename packages
await rename_package("a.b.c", "com.example.network")
# ✅ Renamed 15 classes

await rename_package("a.b.d", "com.example.crypto")
# ✅ Renamed 8 classes

await rename_package("a.b.e", "com.example.database")
# ✅ Renamed 12 classes

# Verify
updated_classes = await get_all_classes()
```

**Result:**
```
✅ REFACTORING COMPLETE

Before:
├── a.b.c (15 classes)
├── a.b.d (8 classes)
└── a.b.e (12 classes)

After:
├── com.example.network (15 classes)
├── com.example.crypto (8 classes)
└── com.example.database (12 classes)

Total updates: 35 classes, 487 references
```

---

## Malware Analysis

### Example 7: Behavioral Analysis

**Goal:** Identify potentially malicious behaviors.

**Prompt:**
```
Scan for suspicious behaviors:

1. Check for dynamic code loading
2. Find data exfiltration code
3. Identify anti-analysis techniques
4. Locate obfuscated strings
5. Check for root detection
```

**Workflow:**

```python
# Check 1: Dynamic code loading
dex_search = await search_classes_by_keyword("DexClassLoader")
# Found: com.malware.Loader

loader_class = await get_class_source("com.malware.Loader")
# Downloads and executes remote DEX file

# Check 2: Data exfiltration
http_search = await search_classes_by_keyword("HttpURLConnection")
# Found: com.malware.Uploader

uploader_xrefs = await get_xrefs_to_class("com.malware.Uploader")
# Called from multiple locations, sends device data

# Check 3: Anti-analysis
debug_search = await search_classes_by_keyword("isDebuggerConnected")
# Found: com.malware.AntiDebug

anti_debug = await get_class_source("com.malware.AntiDebug")
# Checks for debugger, emulator, and root

# Check 4: String obfuscation
string_methods = await search_method_by_name("decryptString")
# Found: com.malware.StringObf.decryptString()

# Get smali for analysis
smali = await get_smali_of_class("com.malware.StringObf")

# Check 5: Root detection
root_search = await search_classes_by_keyword("su binary")
# Found: com.malware.RootCheck
```

**Report:**
```
🔴 MALWARE DETECTED

Malicious Behaviors:
1. ✓ Dynamic DEX loading from remote server
2. ✓ Exfiltrates IMEI, contacts, SMS
3. ✓ Anti-debugging/anti-emulator checks
4. ✓ String obfuscation (AES encrypted strings)
5. ✓ Root detection with privilege escalation attempt

C2 Servers:
- http://malicious-c2.com/gate.php
- http://192.168.1.100:8080/upload

Risk Level: CRITICAL
Recommendation: Quarantine and report to authorities
```

---

### Example 8: Permission Analysis

**Goal:** Identify permission abuse and privacy risks.

**Prompt:**
```
Analyze permissions and privacy:

1. List all declared permissions
2. For each permission, find usage in code
3. Identify overprivileged permissions
4. Check for privacy violations
```

**Workflow:**
```python
# Get manifest
manifest = await get_android_manifest()
permissions = manifest['permissions']

analysis = {}
for perm in permissions:
    # Find where permission is used
    perm_name = perm.split('.')[-1]  # e.g., CAMERA

    # Search for related code
    usage = await search_classes_by_keyword(perm_name.lower())

    analysis[perm] = {
        'declared': True,
        'used': len(usage['results']) > 0,
        'usage_count': len(usage['results']),
        'locations': usage['results']
    }

# Generate report
for perm, data in analysis.items():
    if data['declared'] and not data['used']:
        print(f"⚠️ Unused permission: {perm}")
    elif data['used']:
        print(f"✓ {perm}: Used in {data['usage_count']} locations")
```

**Output:**
```
📊 PERMISSION ANALYSIS

Declared Permissions: 12

✓ INTERNET: Used in 8 locations
  - NetworkManager.makeRequest()
  - Uploader.sendData()
  - AdSDK.loadAds()

⚠️ CAMERA: Declared but NEVER used
⚠️ READ_CONTACTS: Declared but NEVER used

✓ ACCESS_FINE_LOCATION: Used in 2 locations
  - LocationTracker.getLocation()
  - AnalyticsSDK.trackUser()

🔴 PRIVACY CONCERNS:
1. Location accessed for analytics (not disclosed)
2. CAMERA/CONTACTS permissions unused (should remove)
3. Ad SDK has INTERNET access (data sharing possible)

Recommendation:
- Remove unused CAMERA and READ_CONTACTS permissions
- Disclose location usage in privacy policy
- Review Ad SDK data collection practices
```
