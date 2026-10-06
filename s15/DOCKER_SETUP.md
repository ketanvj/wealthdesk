# Docker Setup — Session 15

Install Docker Desktop before Saturday's session. We'll build and run the image together in class.

---

## macOS

1. Go to **docker.com/products/docker-desktop** and download the correct version for your chip:
   ```bash
   uname -m
   # arm64  → download "Apple Silicon"
   # x86_64 → download "Intel Chip"
   ```
2. Open the `.dmg`, drag **Docker.app** to Applications, then launch it.
3. Wait for the whale icon in the menu bar to stop animating — it should say *"Docker Desktop is running"*.

**Verify:**
```bash
docker run --rm hello-world
```
You should see `Hello from Docker!`

---

## Windows

1. Open **PowerShell as Administrator** and run:
   ```powershell
   wsl --install
   ```
   Restart your PC when prompted.

   > If you see *"Virtualization not enabled"*, search *"enable virtualization [your laptop model]"* for BIOS instructions.

2. Go to **docker.com/products/docker-desktop**, download and run `Docker Desktop Installer.exe` — keep *"Use WSL 2 instead of Hyper-V"* checked.
3. Launch Docker Desktop and wait until the system tray icon shows *"Docker Desktop is running"*.

   > If prompted for a WSL 2 kernel update, download it from **aka.ms/wsl2kernel** and re-launch.

**Verify:**
```powershell
docker run --rm hello-world
```

---

## Linux (Ubuntu / Debian)

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

Run Docker without sudo:
```bash
sudo usermod -aG docker $USER
newgrp docker
```

**Verify:**
```bash
docker run --rm hello-world
```

> **Fedora / RHEL:** use `dnf` and the Docker RPM repo. **Arch:** `sudo pacman -S docker`

---

## You're ready if...

`docker run --rm hello-world` prints `Hello from Docker!`
