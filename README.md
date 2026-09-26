# NorthPeak Components: Supplier Cost Tool

A small tool that replaces part of the manual "open each supplier file and copy numbers into a
spreadsheet" process: a validated bulk-upload pipeline, a cost-review screen with an audit trail,
and a one-line risk note per supplier. All data is fictional. The requirements come from the case-study brief.

## Run it

Needs Python 3.9+ and Node 20+ (Node is only needed to build the React frontend).

```bash
# 1. Create and activate a virtual environment, then install the Python packages
python3 -m venv .venv
source .venv/bin/activate                    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Build the frontend (needs Node 20+; see below if you don't have it)
cd frontend && npm install && npm run build && cd ..

# 3. Start the app
python -m src serve                          # http://127.0.0.1:5000  (API + built React app)
```

Activate the environment (`source .venv/bin/activate`) in every new terminal before running `python`,
`pip` or `npm` commands from this README; the commands below assume it is active. Without activating,
`python` is the system Python, which does not have the packages installed. (Alternatively, call
`.venv/bin/python` and `.venv/bin/pytest` directly.) Type `deactivate` to leave the environment.

**No Node installed?** This puts Node and npm inside the virtual environment (no admin rights, no global
install). Run it after step 1, then continue with step 2:

```bash
pip install nodeenv && nodeenv -p --node=22.11.0
```

