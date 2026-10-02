# NetScope Binary Wire Protocol & Framing

## 1. Framing Format
All messages exchanged over the TCP data channel use 4-byte big-endian framing:

```text
+-----------------------+------------------------------------------+
|  Length (4 Bytes, BE)  |           Payload (Length Bytes)         |
+-----------------------+------------------------------------------+
```

## 2. Message Types

### Metadata Header (JSON)
Before data streaming, sender transmits:
```json
{
  "transfer_id": "T-001",
  "pair_id": "P-001",
  "filename": "sample.bin",
  "size_bytes": 104857600,
  "sha256": "39a1feba0c4b...",
  "sender": "Phone-A",
  "receiver": "Laptop-B"
}
```

### Data Chunks
Payload chunks are sliced at 64 KB (65,536 bytes) framed with their 4-byte length prefix.

### Verification Acknowledgment
Upon receiving the last chunk, receiver verifies SHA-256 and responds with:
```json
{
  "status": "COMPLETED",
  "sha256_match": true,
  "bytes_received": 104857600
}
```
