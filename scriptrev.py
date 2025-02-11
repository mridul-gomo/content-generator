import os
import openai
import gspread
import time
import logging
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from google.oauth2 import service_account
from webdriver_manager.chrome import ChromeDriverManager

# Load environment variables from config.env
load_dotenv()

# Securely load API keys and IDs
openai_api_key = os.getenv("OPENAI_API_KEY")
sheet_id = os.getenv("SHEET_ID")
service_account_file = os.getenv("GOOGLE_CREDENTIALS")

openai.api_key = openai_api_key

# Configure logging for debugging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load Google Sheets API credentials securely
def load_gsheet_credentials():
    try:
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
        creds = service_account.Credentials.from_service_account_file(service_account_file, scopes=SCOPES)
        client = gspread.authorize(creds)
        logging.info("Google Sheets credentials loaded successfully.")
        return client
    except Exception as e:
        logging.exception("Failed to load Google Sheets credentials:")
        raise

# Scrape page content using Selenium and BeautifulSoup
def scrape_page_content(url):
    try:
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')

        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
        driver.get(url)
        logging.info(f"Navigating to URL: {url}")

        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
        time.sleep(2)

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        driver.quit()

        body = soup.find('body')
        if body:
            # Remove unwanted tags
            for tag in body(['header', 'footer', 'script', 'nav']):
                tag.extract()
            logging.info("Successfully extracted body content.")
            return body.get_text(strip=True)
        else:
            logging.warning("No body tag found in the HTML.")
            return ''
    except Exception as e:
        logging.exception(f"Error occurred while scraping URL {url}:")
        return ''

# Process the generated content: split into meta title, meta description, and content
def process_generated_content(generated_content):
    lines = generated_content.split('\n')
    meta_title = lines[0].strip() if len(lines) > 0 else ""
    meta_desc = lines[1].strip() if len(lines) > 1 else ""
    final_content = "\n".join([line.strip() for line in lines[2:]]) if len(lines) > 2 else ""
    return meta_title, meta_desc, final_content

# Generate content using OpenAI API
def generate_openai_content(prompt, content_a, content_b):
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"Content A: {content_a}\nContent B: {content_b}"}
            ],
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.exception("Failed to generate content with OpenAI:")
        return ""

# Update Google Sheets with generated content in columns D, E, and F
def update_gsheet(sheet, row, meta_title, meta_desc, new_content):
    try:
        sheet.update_cell(row, 4, meta_title)     # Column D
        sheet.update_cell(row, 5, meta_desc)      # Column E
        sheet.update_cell(row, 6, new_content)    # Column F
        logging.info(f"Successfully updated row {row} in Google Sheets.")
    except Exception as e:
        logging.exception(f"Failed to update Google Sheets at row {row}:")

# Main function
def main():
    try:
        client = load_gsheet_credentials()
        sheet = client.open_by_key(sheet_id).sheet1

        rows = sheet.get_all_values()
        for idx, row in enumerate(rows[1:], start=2):
            url = row[0].strip() if len(row) > 0 else ""
            provided_content = row[1].strip() if len(row) > 1 else ""
            keywords = row[2].strip() if len(row) > 2 else ""

            if url:
                logging.info(f"Processing row {idx} with URL: {url}")
                scraped_content = scrape_page_content(url)

                if scraped_content:
                    prompt = (
                        "You are an SEO expert. Please generate webpage content in Danish with the following structure:\n\n"
                        "Meta Title: A concise title around 60-70 characters (do not include labels).\n"
                        "Meta Description: A short description around 130-150 characters (do not include labels).\n"
                        "Optimized Content: A detailed, engaging, and persuasive text divided into clear paragraphs. "
                        "Naturally integrate the provided keywords and ensure that the phrase 'Volvo genuine parts' is included.\n\n"
                        "Do not include any extra labels or example texts in your output."
                    )
                    if keywords:
                        prompt += f" Also, include the following keywords: {keywords}."
                    
                    generated_content = generate_openai_content(prompt, scraped_content, provided_content)

                    if generated_content:
                        meta_title, meta_desc, final_content = process_generated_content(generated_content)
                        update_gsheet(sheet, idx, meta_title, meta_desc, final_content)
                    else:
                        logging.warning(f"No content generated for row {idx}.")
                else:
                    logging.warning(f"No content could be scraped from URL for row {idx}.")
            else:
                logging.warning(f"No URL found for row {idx}.")
    except Exception as e:
        logging.exception("An error occurred in the main process:")

if __name__ == "__main__":
    main()
