# Docker Setup — Session 15

Get Docker running on your machine before Saturday's session.

---

## Prerequisites (all platforms)

- Your `GROQ_API_KEY` in `cohort-1/wealthdesk/.env`
- The course repo cloned locally (`s15/solution/` folder must exist)
- At least 4 GB free disk space
- A stable internet connection for the first build

---

## macOS

### 1. Install Docker Desktop

1. Go to **docker.com/products/docker-desktop** and download the correct version for your chip:
   ```bash
   uname -m
   # arm64  → download "Apple Silicon"
   # x86_64 → download "Intel Chip"
   ```
2. Open the `.dmg`, drag **Docker.app** to Applications, then launch it.
3. Wait for the whale icon in the menu bar to stop animating — it should say *"Docker Desktop is running"*.

### 2. Verify

```bash
docker --version
docker run --rm hello-world
```

You should see `Hello from Docker!`

### 3. Build the image

```bash
cd cohort-1/wealthdesk/s15/solution
docker build -t wealthdesk .
```

> First build takes 5–8 minutes. Subsequent builds are ~30 seconds (layers are cached).

### 4. Run it

```bash
docker run -p 8501:8501 --env-file ../../.env wealthdesk
```

Open **http://localhost:8501** — you should see the WealthDesk chat UI.  
Press `Ctrl+C` to stop.

---

## Windows

### 1. Enable WSL 2

Open **PowerShell as Administrator** and run:

```powershell
wsl --install
```

Restart your PC when prompted.

> If you see *"Virtualization not enabled"*, enable it in your BIOS/UEFI settings. Search *"enable virtualization [your laptop model]"* if you're unsure how.

### 2. Install Docker Desktop

1. Go to **docker.com/products/docker-desktop** and download the Windows installer.
2. Run `Docker Desktop Installer.exe` — keep *"Use WSL 2 instead of Hyper-V"* checked.
3. Launch Docker Desktop from the Start menu and wait until the system tray icon shows *"Docker Desktop is running"*.

If prompted to install the WSL 2 kernel update, download it from **aka.ms/wsl2kernel** and re-launch.

### 3. Verify

```powershell
docker --version
docker run --rm hello-world
```

### 4. Build the image

```powershell
cd cohort-1\wealthdesk\s15\solution
docker build -t wealthdesk .
```

### 5. Run it

```powershell
docker run -p 8501:8501 -e GROQ_API_KEY=gsk_your_key_here wealthdesk
```

Open **http://localhost:8501**.  
Press `Ctrl+C` to stop.

---

## Linux (Ubuntu / Debian)

### 1. Install Docker Engine

```bash
# Remove old versions
sudo apt-get remove docker docker-engine docker.io containerd runc

# Add Docker's official repository
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
| sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
```

> **Fedora / RHEL:** use `dnf` and the Docker RPM repo.  
> **Arch:** `sudo pacman -S docker`

### 2. Run Docker without sudo

```bash
sudo usermod -aG docker $USER
newgrp docker
```

Log out and back in if `newgrp` doesn't take effect.

### 3. Start and verify

```bash
sudo systemctl start docker
docker --version
docker run --rm hello-world
```

### 4. Build the image

```bash
cd cohort-1/wealthdesk/s15/solution
docker build -t wealthdesk .
```

### 5. Run it

```bash
docker run -p 8501:8501 --env-file ../../.env wealthdesk
```

Open **http://localhost:8501**.  
Press `Ctrl+C` to stop.

---

## It's working if...

- The WealthDesk chat UI loads at `http://localhost:8501`
- Asking *"What is the home loan rate at BNB?"* returns a number
- `docker images` shows a `wealthdesk` entry (~1.2 GB)

---

## Common issues

| Problem | Fix |
|---|---|
| Port 8501 already in use | Use `-p 8502:8501` and open `http://localhost:8502` |
| "No space left on device" during build | Run `docker system prune -f` then rebuild |
| GROQ_API_KEY not found | Pass it directly: `-e GROQ_API_KEY=gsk_...` |
| Linux: permission denied | Run `sudo usermod -aG docker $USER` then log out and back in |
| Build hangs at `ingest.py` | It's not hung — embedding 5 documents takes 2–3 minutes on first run |
