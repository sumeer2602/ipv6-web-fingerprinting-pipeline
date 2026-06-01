# Stage 3 — Entropy Calculation

Compute Shannon entropy for domains and IP addresses. These values weight the
fingerprint matching in Stage 4 — rare IPs contribute more to the score.

## Scripts

| Script | Purpose |
|---|---|
| `domain_entropy.py` | Per-domain entropy from domain fingerprint files |
| `ip_entropy.py` | Per-IP entropy from a zdns AAAA or A snapshot |

## Run

```bash
# Domain entropy (from enrollment domain fingerprints)
python domain_entropy.py \
    --domain-fp-dir /storage/v6wft/domain_based/chrome/1 \
    --output domain_entropy.csv

# IPv6 entropy (for dual-stack matching score)
python ip_entropy.py \
    --zdns-file /storage/v6wft/domains/AAAA_<timestamp>.gz \
    --output ip_entropy_AAAA.csv

# IPv4 entropy (for IPv4 matching score)
python ip_entropy.py \
    --zdns-file /storage/v6wft/domains/A_<timestamp>.gz \
    --output ip_entropy_A.csv
```

## What Entropy Means Here

- **High entropy** = the domain/IP is rare → appears in few fingerprints → strong signal
- **Low entropy** = the domain/IP is common (e.g. CDN shared by many sites) → weak signal

`fp_testing_opt.py` uses these values to weight IP matches:
`score = sum(entropy[ip] for ip in matching_secondary_ips)`

The higher the total score, the more confident the match.

## Output Columns

`domain_entropy.csv`: `domain, entropy`  
`ip_entropy_AAAA.csv`: `ip, entropy`  
`ip_entropy_A.csv`: `ip, entropy`
