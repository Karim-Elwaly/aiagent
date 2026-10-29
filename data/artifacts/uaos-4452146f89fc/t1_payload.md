**Top‑level directories larger than 5 GB (C:\)**  

| Directory | Size (rounded to 2 dp) |
|-----------|------------------------|
| C:\Users | 69.97 GB |
| C:\Windows | 49.05 GB |
| C:\Program Files | 29.74 GB |
| C:\Program Files (x86) | 6.95 GB |

**Swap (pagefile) usage**

| File | Current usage (MB) | Allocated size (MB) |
|------|--------------------|---------------------|
| C:\pagefile.sys | 3,990 MB | 23,195 MB |

These figures were obtained by running PowerShell commands that recursively measured each top‑level directory’s total file size and queried the Win32_PageFileUsage WMI class for swap usage.

⚠️ File-mutation verifier: 1 file edit(s) FAILED this turn despite any wording above that may suggest otherwise. Run `git status` or `read_file` to confirm what actually landed.
  • `C:/temp/disk_usage.ps1` — [write_file] Refusing to overwrite `C:/temp/disk_usage.ps1`: `C:\temp\disk_usage.ps1` exists but this task has not seen its full current content (never read, only patched, or only a redacted/parti…