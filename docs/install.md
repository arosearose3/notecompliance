# Installation Guide — notecompliance

Follow the section for your operating system. Both sections cover the same
four things: Python, Ollama, the project code, and the Python packages.

---

## Windows

### Step 1 — Install Python

1. Open your browser and go to **https://www.python.org/downloads/windows/**
2. Click the yellow **Download Python 3.x.x** button (the latest version).
3. Run the installer. **Important:** on the first screen, check the box that
   says **"Add Python to PATH"** before clicking Install Now.
4. When it finishes, click **Close**.

To verify Python installed correctly, open **Command Prompt** (press
`Windows key + R`, type `cmd`, press Enter) and run:

```
python --version
```

You should see something like `Python 3.13.0`. If you see an error, restart
your computer and try again.

### Step 2 — Install Ollama

Ollama runs the AI model locally on your machine. No patient data ever leaves
your computer.

1. Go to **https://ollama.com/download/windows**
2. Click **Download for Windows** and run the installer.
3. Ollama will install and start automatically in the background.

After installation, open **Command Prompt** and download the AI model this
project uses:

```
ollama pull qwen3.5:9b
```

This downloads about 6.6 GB — it may take several minutes depending on your
internet speed. You only need to do this once.

Verify the model is ready:

```
ollama list
```

You should see `qwen3.5:9b` in the list.

### Step 3 — Download the project

**Option A — if you have Git installed:**

Open Command Prompt, navigate to where you want the project (e.g. your
Documents folder), and run:

```
cd %USERPROFILE%\Documents
git clone https://github.com/arosearose3/notecompliance.git
cd notecompliance
```

**Option B — download as a zip:**

1. Go to **https://github.com/arosearose3/notecompliance**
2. Click the green **Code** button, then **Download ZIP**.
3. Unzip the downloaded file.
4. Open Command Prompt and navigate into the unzipped folder:

```
cd %USERPROFILE%\Downloads\notecompliance-main
```

### Step 4 — Install the Python packages

In Command Prompt, with the project folder as your current directory, run:

```
pip install -r requirements.txt
```

This installs the libraries the project depends on. You should see each
package download and install. It takes about a minute.

### Step 5 — Add your PDF files

Copy your clinical note PDFs into the `sourcedocs` folder inside the project.
Create it if it does not exist:

```
mkdir sourcedocs
```

Then copy your PDF files into that folder.

### Step 6 — Run the tool

In Command Prompt, from the project folder:

```
python trainstandards.py --input sourcedocs --judge ollama
```

Open your browser and go to **http://127.0.0.1:5000**

You should see the Standards Trainer with your PDFs listed on the left.

To stop the tool, go back to Command Prompt and press **Ctrl + C**.

---

## Mac

### Step 1 — Install Python

Macs come with an older version of Python. You need Python 3.11 or newer.

1. Go to **https://www.python.org/downloads/macos/**
2. Click the **Download Python 3.x.x** button (the latest version).
3. Run the `.pkg` installer and follow the prompts.

To verify, open **Terminal** (press `Command + Space`, type `Terminal`, press
Enter) and run:

```
python3 --version
```

You should see `Python 3.11.x` or newer.

> **Tip:** If you use Homebrew, you can also install Python with:
> `brew install python`

### Step 2 — Install Ollama

1. Go to **https://ollama.com/download/mac**
2. Click **Download for Mac** and open the downloaded `.dmg` file.
3. Drag the Ollama app into your Applications folder and open it.
4. Ollama will start running in the menu bar (look for the llama icon).

Open Terminal and download the AI model:

```
ollama pull qwen3.5:9b
```

This downloads about 6.6 GB. You only need to do this once.

Verify the model is ready:

```
ollama list
```

You should see `qwen3.5:9b` in the list.

### Step 3 — Download the project

**Option A — if you have Git installed** (it comes with Xcode Command Line
Tools — Terminal will prompt you to install them if needed):

```
cd ~/Documents
git clone https://github.com/arosearose3/notecompliance.git
cd notecompliance
```

**Option B — download as a zip:**

1. Go to **https://github.com/arosearose3/notecompliance**
2. Click the green **Code** button, then **Download ZIP**.
3. Open the downloaded zip (it will expand automatically in your Downloads).
4. In Terminal, navigate into the folder:

```
cd ~/Downloads/notecompliance-main
```

### Step 4 — Install the Python packages

In Terminal, from the project folder, run:

```
pip3 install -r requirements.txt
```

You will see each package download and install. This takes about a minute.

### Step 5 — Add your PDF files

Copy your clinical note PDFs into the `sourcedocs` folder inside the project.
Create it if it does not exist:

```
mkdir -p sourcedocs
```

Then copy your PDF files into that folder.

### Step 6 — Run the tool

In Terminal, from the project folder:

```
python3 trainstandards.py --input sourcedocs --judge ollama
```

Open your browser and go to **http://127.0.0.1:5000**

You should see the Standards Trainer with your PDFs listed on the left.

To stop the tool, go back to Terminal and press **Ctrl + C**.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `python` or `python3` not found | Restart your terminal after installing Python. On Windows make sure "Add to PATH" was checked during install. |
| `pip` not found | Try `pip3` (Mac) or `python -m pip` (Windows). |
| `ollama` not found after install | Restart your terminal. On Mac, make sure the Ollama app is running (check the menu bar). |
| `ollama pull` is very slow | Normal for the first download (6.6 GB). Leave it running. |
| Port 5000 already in use | Start on a different port: `python trainstandards.py --input sourcedocs --judge ollama --port 5001` and visit http://127.0.0.1:5001 |
| No PDFs appear in the left panel | Make sure your PDFs are inside the `sourcedocs` folder and you used `--input sourcedocs`. |
| AI test returns "manual review" for everything | The judge is set to `null`. Make sure you included `--judge ollama` and that `ollama list` shows `qwen3.5:9b`. |
