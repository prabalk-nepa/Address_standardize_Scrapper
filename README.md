# Google Maps Address Extractor

A Streamlit app that takes an Excel/CSV file with address fields, searches Google Maps for each row, and returns standardized addresses.

## Prerequisites
- Python 3.10+
- Google Chrome browser installed

## Setup & Run
```bash
python -m venv web_scrappe_venv
web_scrappe_venv\Scripts\activate        # On Windows
pip install -r requirements.txt
streamlit run app.py
```

## Usage
1. Upload a CSV/Excel file with columns: `ID, Customer Code, Display Partner, Email, Phone, Mobile, Street, Street2, City, State, Zip, Country`.
2. Toggle headless mode, adjust delay and batch size, then click **Start Processing**.
3. The app saves progress after each batch so you can resume if interrupted.
4. Download the results as Excel or CSV when done.
