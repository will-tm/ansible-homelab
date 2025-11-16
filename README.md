# Ansible Homelab Maintenance

Automated maintenance playbook for homelab environments running Debian/Ubuntu-based systems, Docker containers, and Proxmox LXC containers.

## Features

- **System Updates**: Automated apt package updates with intelligent cleanup
- **Docker Cleanup**: Comprehensive pruning of Docker images, containers, volumes, networks, and build cache
- **LXC Optimization**: Filesystem trimming for Proxmox LXC containers
- **Smart Detection**: Automatically detects available services (Docker, LXC, custom update scripts)
- **Low Disk Space Handling**: Proactive cache cleanup and disk space warnings
- **Reboot Notifications**: Alerts when system reboots are required
- **Custom Update Scripts**: Supports LXC containers with built-in update commands

## Requirements

### System Requirements
- Ansible 2.9 or higher
- Debian/Ubuntu-based target systems
- Python 3.6+ on target hosts

### Ansible Collections
```bash
ansible-galaxy collection install community.docker
```

### Target Host Requirements
- **For all hosts**: apt package manager
- **For Docker cleanup**: Docker CE or Docker.io installed
- **For LXC tasks**: Proxmox VE with LXC containers

## Installation

1. Clone this repository:
```bash
git clone <repository-url>
cd ansible-homelab
```

2. Install required Ansible collections:
```bash
ansible-galaxy collection install community.docker
```

3. Configure your inventory file with target hosts:
```ini
# inventory/hosts
[homelab]
proxmox-host ansible_host=192.168.1.10
lxc-container-1 ansible_host=192.168.1.11
docker-host ansible_host=192.168.1.12
```

4. Test connectivity:
```bash
ansible all -i inventory/hosts -m ping
```

## Usage

### Run Full Maintenance
```bash
ansible-playbook -i inventory/hosts main.yml
```

### Run with Ansible Semaphore
1. Create a new project in Semaphore pointing to this repository
2. Add your inventory
3. Create a template using `main.yml` as the playbook
4. Schedule or run manually

### Selective Execution with Tags

**Run only apt updates:**
```bash
ansible-playbook -i inventory/hosts main.yml --tags apt-update
```

**Run only Docker cleanup:**
```bash
ansible-playbook -i inventory/hosts main.yml --tags docker-cleanup
```

**Run only LXC filesystem trim:**
```bash
ansible-playbook -i inventory/hosts main.yml --tags lxc
```

**Skip specific tasks:**
```bash
ansible-playbook -i inventory/hosts main.yml --skip-tags docker
```

**Multiple tags:**
```bash
ansible-playbook -i inventory/hosts main.yml --tags "apt,docker"
```

### Available Tags

| Tag | Description |
|-----|-------------|
| `apt-update`, `apt`, `updates` | System package updates |
| `docker-cleanup`, `docker`, `cleanup` | Docker resource cleanup |
| `lxc-filesystem-trim`, `lxc`, `trim` | LXC filesystem trimming |

## Configuration

### Variables

You can customize behavior by setting variables in `main.yml` or passing them via command line:

| Variable | Default | Description |
|----------|---------|-------------|
| `maintenance_verbose` | `false` | Enable detailed environment information output |

**Example with verbose output:**
```bash
ansible-playbook -i inventory/hosts main.yml -e "maintenance_verbose=true"
```

### Disk Space Threshold

The playbook warns when available disk space falls below 512 MB. This threshold is set in `tasks/apt-update.yml:42`:

```yaml
- disk_space_available.stdout | int < 512000  # 512 MB in KB
```

To adjust, modify the value (in kilobytes).

## How It Works

### APT Update Process (`tasks/apt-update.yml`)

1. **Custom Update Detection**: Checks for `/usr/local/bin/update` script (common in LXC containers)
2. **If custom update exists**: Runs the custom script and skips standard apt tasks
3. **If no custom update**:
   - Runs `apt clean` to free up cache space
   - Updates apt cache (with 1-hour cache validity)
   - Checks available disk space and warns if < 512 MB
   - Performs full system upgrade
   - Removes unnecessary packages (autoremove + autoclean + purge)
4. **Always**: Checks if reboot is required and displays notification
5. **Summary**: Shows upgrade results

### Docker Cleanup Process (`tasks/docker-cleanup.yml`)

Uses native `community.docker.docker_prune` module for reliable cleanup:

1. Captures disk usage before cleanup
2. Prunes in order:
   - Docker images (including non-dangling)
   - Stopped containers
   - Unused volumes
   - Unused networks
   - Build cache
3. Captures disk usage after cleanup
4. Displays summary of what was pruned

### LXC Filesystem Trim (`tasks/lxc-filesystem-trim.yml`)

1. Lists all LXC containers using `pct list`
2. Parses container information (ID, status, name)
3. Filters for only **running** containers
4. Runs `pct fstrim` on each running container
5. Displays count of trimmed containers

**Why only running containers?**
Trimming stopped containers can cause issues, and running containers benefit most from filesystem optimization.

## Playbook Structure

```
ansible-homelab/
├── main.yml                      # Main playbook
├── tasks/
│   ├── apt-update.yml           # System update tasks
│   ├── docker-cleanup.yml       # Docker cleanup tasks
│   └── lxc-filesystem-trim.yml  # LXC trim tasks
├── inventory/
│   └── hosts                     # Your inventory file
└── README.md
```

## Execution Flow

```
Pre-tasks:
  ├── Display start time
  ├── Gather package facts
  ├── Detect Docker installation
  ├── Detect LXC availability
  └── Display environment summary (if verbose)

Tasks:
  ├── APT updates (always runs)
  ├── Docker cleanup (if Docker installed)
  └── LXC trim (if LXC available)

Post-tasks:
  └── Display completion time
```

## Troubleshooting

### "docker_prune module not found"
**Solution**: Install the community.docker collection:
```bash
ansible-galaxy collection install community.docker
```

### "Insufficient disk space" during apt upgrade
**Solution**: The playbook now runs `apt clean` first. If you still see issues, manually clean:
```bash
ansible all -i inventory/hosts -m shell -a "apt clean && apt autoclean"
```

### LXC trim not running
**Check**:
1. Verify `/usr/sbin/pct` exists on the host
2. Ensure containers are running: `pct list`
3. Run with verbose: `-vvv` to see detection output

### Custom update script not detected
**Check**:
- Script location: `/usr/local/bin/update`
- Script is executable: `chmod +x /usr/local/bin/update`
- Verify in playbook output: look for "Custom update command executed"

## Best Practices

1. **Schedule Regular Runs**: Use Semaphore or cron to run weekly
2. **Test First**: Run on a single host before rolling out to all systems
3. **Monitor Disk Space**: Watch for low space warnings, especially on LXC containers
4. **Review Reboot Notifications**: Check for systems requiring reboots after updates
5. **Backup Before Major Updates**: Consider snapshots for LXC containers before maintenance

## Safety Features

- **Non-destructive**: All cleanup operations only remove unused resources
- **Error handling**: Tasks continue even if individual steps fail
- **Conditional execution**: Only runs tasks relevant to each system
- **Idempotent**: Safe to run multiple times without side effects
- **Smart caching**: Skips apt update if cache is fresh (< 1 hour)
- **Running containers only**: LXC trim only targets running containers

## Example Output

```
TASK [Display playbook start time]
ok: [proxmox-host] => {
    "msg": "Starting homelab maintenance at 2025-11-16T10:30:00Z"
}

TASK [Clean apt cache to free up space]
changed: [proxmox-host]

TASK [Fully upgrade all packages to the latest version]
changed: [proxmox-host]

TASK [Display reboot notification]
ok: [proxmox-host] => {
    "msg": "WARNING: System reboot is required after updates!"
}

TASK [Prune Docker images]
changed: [docker-host]

TASK [Display Docker cleanup summary]
ok: [docker-host] => {
    "msg": "Docker cleanup completed:\n- Images pruned: True\n- Containers pruned: True..."
}

TASK [Display LXC trim summary]
ok: [proxmox-host] => {
    "msg": "Trimmed 5 running LXC container(s)"
}
```

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License - feel free to use and modify for your homelab needs.

## Acknowledgments

- Designed for use with [Ansible Semaphore](https://www.ansible-semaphore.com/)
- Compatible with containers from [tteck's Proxmox Scripts](https://tteck.github.io/Proxmox/)
