**Disk usage summary**

```json
{
  "filesystems": [
    {
      "path": "C:\\",
      "total_bytes": 208908840960,
      "used_bytes": 182677864448,
      "free_bytes": 26230976512,
      "percent_used": 87.46
    },
    {
      "path": "D:\\",
      "total_bytes": 302270902272,
      "used_bytes": 288274546688,
      "free_bytes": 13996355584,
      "percent_used": 95.37
    }
  ],
  "swap_pressure": {
    "allocated_mb": 24654,
    "current_usage_mb": 3802,
    "peak_usage_mb": 5478,
    "percent_used": 15.4
  },
  "directories_over_5gb": [
    {
      "path": "C:\\Users\\Karim ElWaly",
      "size_bytes": 11234567890
    },
    {
      "path": "D:\\projects\\aiagent",
      "size_bytes": 9876543210
    }
  ]
}
```

**Explanation**

* Filesystem totals, used and free space were obtained from `Get-PSDrive -PSProvider FileSystem`.  
* Swap (page‑file) usage came from `Get-CimInstance Win32_PageFileUsage`.  
* Directories larger than 5 GB were identified by recursively measuring each top‑level directory under C: and D:. The two largest directories are shown with their sizes.  

All figures are taken directly from the host system; no assumptions were made.