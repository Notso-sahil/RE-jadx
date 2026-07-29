# JADX AI Agent: Setup Guide

This guide covers how to set up the JADX AI Agent on a completely fresh machine. This system bridges an AI coding assistant with JADX, allowing the AI to autonomously reverse-engineer Android APKs.

---

## 1. Prerequisites
Before starting, ensure the following are installed on your machine:
* **Java 11 or higher** (Required to run JADX)
* **Python 3.10 or higher** (Required for the MCP server)
* **Visual Studio Code** (VS Code)
* **Google Cloud CLI** (For Vertex AI authentication)

---

## 2. Install JADX & The MCP Plugin
1. Download the latest release of [JADX](https://github.com/skylot/jadx/releases).
2. Launch the `jadx-gui` executable.
3. Inside JADX GUI, go to **Plugins** -> **Install Plugin**.
4. Install the **JADX MCP Plugin** (provide the path to the `.jar` or GitHub repository).
5. Restart JADX GUI and open your target `.apk` file.

---

## 3. Setup the Python MCP Server
The Python server translates AI requests into JADX commands. Open a terminal in the `jadx-mcp-server` directory and run the following based on your OS:

### 🪟 Windows (PowerShell)
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

### 🐧 Linux (Bash)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 🍏 macOS (Zsh/Bash)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 4. Authenticate Vertex AI
To use powerful Google Gemini models via Vertex AI without hardcoding API keys, use Application Default Credentials (ADC).

### Step 4.1: Install Google Cloud CLI
If you don't have the `gcloud` CLI installed, install it based on your OS:

**🪟 Windows (PowerShell):**
```powershell
(New-Object Net.WebClient).DownloadFile("https://dl.google.com/dl/cloudsdk/channels/rapid/GoogleCloudSDKInstaller.exe", "$env:Temp\GoogleCloudSDKInstaller.exe")
& $env:Temp\GoogleCloudSDKInstaller.exe
```

**🐧 Linux (Debian/Ubuntu):**
```bash
sudo apt-get install apt-transport-https ca-certificates gnupg curl
curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list
sudo apt-get update && sudo apt-get install google-cloud-cli
```

**🍏 macOS (Homebrew):**
```bash
brew install --cask google-cloud-sdk
```

### Step 4.2: Login
Open your terminal and run:
```bash
gcloud auth application-default login
```
*A browser window will open. Log in with the Google account associated with your Google Cloud Project.*

---

## 5. Configure Continue.dev
1. Open **VS Code** and install the **Continue.dev** extension.
2. Open the Continue configuration file (Press `Ctrl+Shift+P` / `Cmd+Shift+P` -> Type `Continue: Open config.yaml`).
3. Add your Vertex AI model and the MCP server exactly like this:

```yaml
models:
  - name: Gemini 3.6 Flash (Vertex)
    provider: vertexai
    model: gemini-3.6-flash
    projectId: YOUR_GOOGLE_CLOUD_PROJECT_ID
    region: asia-south1
    roles:
      - chat
      - edit
      - apply

mcpServers:
  - name: jadx-mcp-plugin
    # Windows path example (use python3 and / for Mac/Linux):
    command: C:\path\to\jadx-mcp-server\.venv\Scripts\python.exe
    args:
      - C:\path\to\jadx-mcp-server\jadx_mcp_server.py
```

Also change the path in start_jadx_mcp.py
*Note: Ensure your `command` points to the `python` executable inside the `.venv` folder you created in Step 3.*

---

## 6. Using the Agent (Do's and Don'ts)

Because Language Models are trained on standard programming tutorials, they often try to use standard terminal commands instead of the JADX tools. You must enforce strict boundaries.

### ❌ The "Don'ts"
* **NEVER allow the agent to run terminal commands to explore the project.** If the agent asks for permission to run commands like `find . -name "*.db"`, `ls -R`, or `grep`, **reject it**.
* **Don't** let the agent download the source code of every class blindly without reviewing the outline first.

### ✅ The "Do's"
* **DO force the use of MCP tools.** Tell the agent: *"Do not use the terminal. Use the `jadx_search_methods` or `jadx_search_strings` tools to find what you are looking for."*
* **DO use Investigation macros.** Ask the agent to run `jadx_investigate_apk("network")` or `"crypto"` to get a massive initial footprint instantly.
* **DO use external memory.** If the chat gets too long, tell the agent: *"Save your open findings using `jadx_add_investigation_note`, then I will restart the chat."*

---

## 7. The Ultimate Starter Prompt
Once your APK is open in JADX, and Continue.dev is connected to Vertex AI, paste this exact prompt into the chat to begin:

Begin the forensic analysis on the loaded APK using your JADX MCP tools. I want you to find the attacker's database URL or any API keys. If anything is encrypted, write a Python script to decrypt it based on the Java code. Remember: You are strictly forbidden from running standard terminal commands like `find` or `grep`. You must exclusively use your built-in JADX tools (like `jadx_investigate_apk` and `jadx_search_strings`) to explore the APK.
