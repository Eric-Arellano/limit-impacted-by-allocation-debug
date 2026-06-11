# Limit impacted by allocation debug

A minimum reproduction of https://github.com/IBM/qauvern/issues/153.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

1. Generate an API key at https://quantum.cloud.ibm.com and export it as an env var:
   ```bash
   export API_KEY=...
   ```
2. Pick an instance at https://quantum.cloud.ibm.com/instances that already has at least 1s of usage in the "Cycle usage" column. Then, copy its CRN and export it as an env var:
   ```bash
   export CRN=...
   ```
3. Run the script and follow the prompts:
   ```bash
   ./run.py
   ```

To run against staging (`test.cloud.ibm.com`) instead of production, set
`STAGING=1` and use an API key and CRN from
https://quantum.test.cloud.ibm.com:

```bash
STAGING=1 ./run.py
```
