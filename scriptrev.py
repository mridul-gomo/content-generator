import os
import openai
import gspread
import json
import logging
from google.oauth2 import service_account
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time

# Configure logging for debugging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Load credentials from GitHub Secrets
openai_api_key = os.getenv("OPENAI_API_KEY")
sheet_id = os.getenv("SHEET_ID")
google_credentials_json = os.getenv("GOOGLE_CREDENTIALS_JSON")

# ✅ Ensure GOOGLE_CREDENTIALS_JSON is not None
if not google_credentials_json:
    logging.error("❌ GOOGLE_CREDENTIALS_JSON is missing or not set in GitHub Secrets.")
    exit(1)

# ✅ Convert Google credentials JSON string into a dictionary
try:
    google_credentials = json.loads(google_credentials_json)
    logging.info("✅ Google credentials loaded successfully.")
except json.JSONDecodeError as e:
    logging.error(f"❌ Error parsing Google credentials JSON: {e}")
    exit(1)

# ✅ Fix: Use the correct Google Sheets API scopes
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

# Authenticate with Google Sheets
def load_gsheet_credentials():
    try:
        creds = service_account.Credentials.from_service_account_info(google_credentials, scopes=SCOPES)
        client = gspread.authorize(creds)
        logging.info("✅ Successfully authenticated with Google Sheets.")
        return client
    except Exception as e:
        logging.exception("❌ Failed to authenticate with Google Sheets:")
        return None

# Scrape page content using Selenium and BeautifulSoup
def scrape_page_content(url):
    try:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.get(url)
        logging.info(f"🌍 Navigating to URL: {url}")

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        driver.quit()

        body = soup.find("body")
        if body:
            for tag in body(["header", "footer", "script", "nav"]):
                tag.extract()
            logging.info("✅ Successfully extracted body content.")
            return body.get_text(strip=True)
        else:
            logging.warning("⚠️ No body tag found in the HTML.")
            return ""
    except Exception as e:
        logging.exception(f"❌ Error occurred while scraping URL {url}:")
        return ""

# Process the generated content: split into meta title, meta description, and content
def process_generated_content(generated_content):
    lines = generated_content.strip().split("\n")
    meta_title = lines[0].strip() if len(lines) > 0 else ""
    meta_desc = lines[1].strip() if len(lines) > 1 else ""
    final_content = "\n".join([line.strip() for line in lines[2:]]) if len(lines) > 2 else ""
    return meta_title, meta_desc, final_content

# ✅ Fixed OpenAI API Call for New Versions
def generate_openai_content(prompt, content_a, content_b):
    try:
        client = openai.OpenAI(api_key=openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Content A: {content_a}\nContent B: {content_b}"}
            ],
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.exception("❌ Failed to generate content with OpenAI:")
        return ""

# ✅ Update Google Sheets with generated content
def update_gsheet(sheet, row, meta_title, meta_desc, new_content):
    try:
        sheet.update_cell(row, 4, meta_title)   # Column D
        sheet.update_cell(row, 5, meta_desc)    # Column E
        sheet.update_cell(row, 6, new_content)  # Column F
        logging.info(f"✅ Successfully updated row {row} in Google Sheets.")
    except Exception as e:
        logging.exception(f"❌ Failed to update Google Sheets at row {row}:")

# ✅ Main function to process data
def main():
    client = load_gsheet_credentials()
    if client is None:
        logging.error("❌ Google Sheets client is None. Exiting script.")
        exit(1)

    try:
        sheet = client.open_by_key(sheet_id).sheet1
    except Exception as e:
        logging.exception(f"❌ Could not open Google Sheet with ID {sheet_id}:")
        return

    rows = sheet.get_all_values()
    for idx, row in enumerate(rows[1:], start=2):
        url = row[0].strip() if len(row) > 0 else ""
        provided_content = row[1].strip() if len(row) > 1 else ""
        keywords = row[2].strip() if len(row) > 2 else ""

        if url:
            logging.info(f"📌 Processing row {idx} with URL: {url}")
            scraped_content = scrape_page_content(url)

            if scraped_content:
                generated_content = generate_openai_content("Generate SEO content", scraped_content, provided_content)

                if generated_content:
                    meta_title, meta_desc, final_content = process_generated_content(generated_content)
                    update_gsheet(sheet, idx, meta_title, meta_desc, final_content)
                else:
                    logging.warning(f"⚠️ No content generated for row {idx}.")
            else:
                logging.warning(f"⚠️ No content could be scraped from URL for row {idx}.")
    
    # ✅ Update status cell to confirm script execution
    sheet.update_acell("A1", "✅ GitHub Workflow Ran Successfully!")
    logging.info("✅ Google Sheet Status Updated!")

if __name__ == "__main__":
    main()
