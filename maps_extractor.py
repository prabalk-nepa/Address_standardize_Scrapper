import logging
import os
import random
import re
import time
from urllib.parse import quote

import pandas as pd
import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class GoogleMapsExtractor:
    def __init__(self, headless=False, sleep_range=(1.5, 3.0)):
        self.driver = None
        self.headless = headless
        self.sleep_min = max(0.3, float(sleep_range[0]))
        self.sleep_max = max(self.sleep_min, float(sleep_range[1]))
        self.maps_base = "https://www.google.com/maps?hl=en&gl=us"
        self.max_load_retries = 2
        self.lookup_type = "direct"

    def setup_driver(self):
        """Initialize undetected Chrome driver."""
        try:
            options = uc.ChromeOptions()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-extensions")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--lang=en-US")
            options.add_experimental_option("prefs", {
                "intl.accept_languages": "en,en_US",
            })

            if self.headless:
                # --headless=new crashes Chrome 144; move window off-screen instead
                options.add_argument("--window-position=-2400,-2400")
            else:
                options.add_argument("--start-maximized")

            self.driver = uc.Chrome(options=options, version_main=144)
            self.driver.set_page_load_timeout(20)
            logger.info("Chrome driver initialized successfully")

            try:
                self.driver.get(self.maps_base)
                time.sleep(3)
                logger.info("Initial Maps page loaded")
            except Exception:
                logger.warning("Initial preload of Google Maps failed; will retry per query.")

            return True
        except Exception as e:
            logger.error(f"Error initializing driver: {e}")
            return False

    def _restart_driver(self):
        """Restart the driver when Maps fails to load."""
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
        self.driver = None
        return self.setup_driver()

    def _human_pause(self):
        """Sleep for a randomized interval within the configured range."""
        delay = random.uniform(self.sleep_min, self.sleep_max)
        time.sleep(delay)

    def _click_first_search_result(self):
        """Click on the first search result in the list."""
        try:
            # Wait for search results feed
            try:
                WebDriverWait(self.driver, 8).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]'))
                )
            except TimeoutException:
                logger.debug("No search results feed found")
                return False

            time.sleep(0.5)

            # Find the first result link
            selectors = [
                'div[role="article"] a.hfpxzc',
                'div.Nv2PK a.hfpxzc',
                'div[role="article"] a[href*="/maps/place/"]',
            ]

            first_result = None
            for sel in selectors:
                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                if elements:
                    first_result = elements[0]
                    break

            if not first_result:
                logger.warning("Could not find first search result")
                return False

            try:
                aria_label = first_result.get_attribute('aria-label')
                logger.info(f"Found first result: {aria_label[:100] if aria_label else 'No label'}")
            except:
                pass

            # Click using JS (most reliable)
            self.driver.execute_script("arguments[0].click();", first_result)
            logger.info("Clicked first result")

            # Wait for place details to appear
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.any_of(
                        EC.presence_of_element_located((By.CSS_SELECTOR, 'button[data-item-id="address"]')),
                        EC.presence_of_element_located((By.CSS_SELECTOR, '[role="main"] [data-item-id]')),
                    )
                )
                logger.info("Place details page loaded")
                return True
            except TimeoutException:
                logger.warning("Click succeeded but place details didn't load")
                return False

        except Exception as e:
            logger.error(f"Error clicking first search result: {e}")
            return False

    def _is_complete_address(self, text):
        """
        Check if the address is COMPLETE with city, state, and ZIP code.
        This prevents accepting partial addresses like '804 N State Rd 7'.
        """
        if not text or len(text) < 20:
            return False

        has_zip = bool(re.search(r'\b\d{5}(-\d{4})?\b', text))
        has_state = bool(re.search(r'\b[A-Z]{2}\b', text))
        has_city = bool(re.search(r',\s*[A-Za-z\s]+,\s*[A-Z]{2}', text))
        has_commas = text.count(',') >= 2

        return has_zip and has_state and (has_city or has_commas)

    def _extract_address_multiple_strategies(self):
        """Try multiple strategies to extract the COMPLETE address from Google Maps."""
        strategies = [
            self._extract_from_place_card,
            self._extract_from_aria_labels,
            self._extract_from_buttons
        ]

        for strategy in strategies:
            try:
                address = strategy()
                if address and address.strip():
                    if self._is_complete_address(address):
                        logger.info(f"Complete address found using {strategy.__name__}: {address}")
                        return address.strip()
                    else:
                        logger.warning(f"Incomplete address rejected from {strategy.__name__}: {address}")
            except Exception as e:
                logger.debug(f"{strategy.__name__} failed: {e}")
                continue

        return None

    def _extract_from_place_card(self):
        """Extract address from the place information card (detail page only)."""
        try:
            WebDriverWait(self.driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, '[role="main"]'))
            )

            try:
                address_button = self.driver.find_element(By.CSS_SELECTOR, 'button[data-item-id="address"]')
                address_div = address_button.find_element(By.CSS_SELECTOR, 'div.Io6YTe.fontBodyMedium')
                text = address_div.text.strip()
                if text:
                    logger.info(f"Extracted from place card button: {text}")
                    return text
            except NoSuchElementException:
                logger.debug("Could not find button[data-item-id='address']")

            try:
                buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button[data-item-id="address"]')
                for button in buttons:
                    aria_label = button.get_attribute('aria-label')
                    if aria_label and 'Address:' in aria_label:
                        address = aria_label.replace('Address:', '').strip()
                        if address:
                            logger.info(f"Extracted from aria-label: {address}")
                            return address
            except:
                pass

            try:
                address_divs = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    'button[data-item-id="address"] div.Io6YTe'
                )
                for div in address_divs:
                    text = div.text.strip()
                    if text and len(text) > 15:
                        logger.info(f"Extracted from Io6YTe div: {text}")
                        return text
            except:
                pass

            try:
                buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button[data-item-id="address"]')
                for button in buttons:
                    divs = button.find_elements(By.TAG_NAME, 'div')
                    for div in divs:
                        text = div.text.strip()
                        if text and len(text) > 20:
                            logger.info(f"Extracted from button div: {text}")
                            return text
            except:
                pass

            return None
        except Exception as e:
            logger.debug(f"_extract_from_place_card error: {e}")
            return None

    def _extract_from_aria_labels(self):
        """Extract address from aria-labels."""
        try:
            elements = self.driver.find_elements(
                By.XPATH,
                '//*[@aria-label and (contains(@aria-label, "Address") or contains(@aria-label, "address"))]'
            )

            for element in elements:
                aria_label = element.get_attribute('aria-label')
                if aria_label:
                    for prefix in ['Address:', 'Address', 'Located at']:
                        if prefix in aria_label:
                            address = aria_label.split(prefix, 1)[1].strip()
                            if len(address) > 20:
                                return address

            return None
        except Exception as e:
            logger.debug(f"_extract_from_aria_labels error: {e}")
            return None

    def _extract_from_buttons(self):
        """Extract address from buttons with data attributes."""
        try:
            buttons = self.driver.find_elements(By.TAG_NAME, 'button')

            for button in buttons:
                data_item_id = button.get_attribute('data-item-id')
                if data_item_id and 'address' in data_item_id.lower():
                    text = button.text.strip()
                    if text and len(text) > 20:
                        return text

                try:
                    nested_divs = button.find_elements(By.TAG_NAME, 'div')
                    for div in nested_divs:
                        text = div.text.strip()
                        if text and len(text) > 20:
                            return text
                except:
                    continue

            return None
        except Exception as e:
            logger.debug(f"_extract_from_buttons error: {e}")
            return None

    def _wait_for_maps_loaded(self, timeout=10):
        """Wait until any Google Maps page element is present."""
        try:
            WebDriverWait(self.driver, timeout).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'button[data-item-id="address"]')),
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[role="main"]')),
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div[role="feed"]')),
                    EC.presence_of_element_located((By.ID, "searchboxinput")),
                    EC.presence_of_element_located((By.XPATH, '//canvas[@aria-label="Map"]')),
                )
            )
            return True
        except TimeoutException:
            return False
        except Exception:
            return False

    def search_address_on_maps(self, address):
        """Search for an address on Google Maps and extract the standard address."""
        try:
            self.lookup_type = "direct"

            encoded_address = quote(address)
            url = f"https://www.google.com/maps/search/{encoded_address}?hl=en&gl=us"

            logger.info(f"Searching for: {address}")

            try:
                self.driver.get(url)
            except TimeoutException:
                logger.warning(f"Page load timed out for: {address}")
            except Exception as e:
                logger.warning(f"Navigation error for: {address}: {e}")
                try:
                    self._restart_driver()
                    self.driver.get(url)
                except Exception:
                    return "N/A", "N/A"

            # Wait for Maps to load any recognizable element
            if not self._wait_for_maps_loaded(timeout=12):
                logger.warning(f"Maps did not load for: {address}")
                return "N/A", "N/A"

            # STEP 1: Check if Maps redirected directly to a place page
            address_text = self._extract_address_multiple_strategies()

            if address_text and self._is_complete_address(address_text):
                logger.info(f"Found address directly: {address_text}")
                self.lookup_type = "direct"
                return address_text, self.lookup_type

            # STEP 2: We got search results instead — click the first one
            logger.info("No direct place page. Clicking first search result...")
            if self._click_first_search_result():
                self.lookup_type = "indirect"
                address_text = self._extract_address_multiple_strategies()

                if address_text and self._is_complete_address(address_text):
                    logger.info(f"Found address after clicking result: {address_text}")
                    return address_text, self.lookup_type

            logger.warning(f"Could not extract address for: {address}")
            return "N/A", "N/A"

        except Exception as e:
            logger.error(f"Error searching for address '{address}': {e}")
            return "N/A", "N/A"

    def _prepare_dataframe(self, df, keep_existing=False):
        """Build helper columns from the source data."""
        required_cols = ['Street', 'Street2', 'City', 'State', 'Zip', 'Display Partner']
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")

        df = df.copy()
        df['street_'] = df['Street'].fillna('').replace('nan', '').astype(str).str.strip()
        street2 = df['Street2'].fillna('').replace('nan', '').astype(str).str.strip()
        df.loc[df['street_'] == '', 'street_'] = street2[df['street_'] == '']

        def build_query(row):
            def clean(val):
                if pd.isna(val):
                    return ""
                text = str(val).strip()
                if text.lower() == "nan":
                    return ""
                text = re.sub(r'\s*\([^)]*\)', '', text).strip()
                return text

            parts = [
                clean(row.get('street_')),
                clean(row.get('City')),
                clean(row.get('State')),
                clean(row.get('Zip')),
            ]
            body = " ".join(part for part in parts if part).strip()

            display_partner = str(row.get('Display Partner', '') or '').strip()
            if display_partner:
                return f"{display_partner} in {body}".strip()
            return body

        df['search_query'] = df.apply(build_query, axis=1)
        df = df.drop_duplicates(subset=['search_query']).reset_index(drop=True)

        if not keep_existing or 'standard_address' not in df.columns:
            df['standard_address'] = "N/A"
        else:
            df['standard_address'] = df['standard_address'].fillna("N/A")

        if not keep_existing or 'lookup_type' not in df.columns:
            df['lookup_type'] = "N/A"
        else:
            df['lookup_type'] = df['lookup_type'].fillna("N/A")

        if not keep_existing or 'processed' not in df.columns:
            df['processed'] = False
        else:
            df['processed'] = df['processed'].fillna(False).astype(bool)

        if not df['processed'].any():
            filled = df['standard_address'].astype(str).str.strip().fillna("")
            df.loc[(filled != "") & (filled.str.upper() != "N/A"), 'processed'] = True

        return df

    def process_file(self, input_file, output_file, progress_callback=None, resume=False, batch_size=10):
        """Process the input file and create output with standard addresses."""
        try:
            if resume and output_file and output_file.endswith(('.csv', '.xlsx', '.xls')) and os.path.exists(output_file):
                if output_file.endswith('.csv'):
                    df = pd.read_csv(output_file)
                else:
                    df = pd.read_excel(output_file)
                df = self._prepare_dataframe(df, keep_existing=True)
                logger.info("Resuming from existing output file.")
            else:
                if input_file.endswith('.csv'):
                    df = pd.read_csv(input_file)
                elif input_file.endswith(('.xlsx', '.xls')):
                    df = pd.read_excel(input_file)
                else:
                    raise ValueError("Unsupported file format. Use CSV or Excel files.")

                df = self._prepare_dataframe(df, keep_existing=False)
                if output_file.endswith('.csv'):
                    df.to_csv(output_file, index=False)
                else:
                    df.to_excel(output_file, index=False)
                logger.info("Created fresh working copy.")

            if not self.setup_driver():
                raise Exception("Failed to initialize Chrome driver")

            total_rows = len(df)
            logger.info(f"Processing {total_rows} addresses...")

            pending_mask = df['processed'].astype(bool) == False
            pending_indices = df.index[pending_mask].tolist()
            base_completed = total_rows - len(pending_indices)

            for batch_start in range(0, len(pending_indices), max(1, int(batch_size))):
                batch_indices = pending_indices[batch_start: batch_start + int(batch_size)]

                for processed_count, idx in enumerate(batch_indices, start=1):
                    query = df.loc[idx, 'search_query']

                    if not query:
                        df.loc[idx, 'standard_address'] = "N/A"
                        df.loc[idx, 'lookup_type'] = "N/A"
                        logger.warning(f"Row {idx+1}: Empty query, skipping")
                    else:
                        address, lookup_type = self.search_address_on_maps(str(query))
                        df.loc[idx, 'standard_address'] = address
                        df.loc[idx, 'lookup_type'] = lookup_type

                    df.loc[idx, 'processed'] = True

                    if progress_callback:
                        processed_so_far = base_completed + batch_start + processed_count
                        progress_callback(processed_so_far, total_rows)

                    self._human_pause()

                if output_file.endswith('.csv'):
                    df.to_csv(output_file, index=False)
                else:
                    df.to_excel(output_file, index=False)
                logger.info(f"Progress saved after batch ending at row {batch_indices[-1] + 1}.")

            if output_file.endswith('.csv'):
                df.to_csv(output_file, index=False)
            else:
                df.to_excel(output_file, index=False)

            logger.info(f"Processing complete! Output saved to: {output_file}")
            return True, df

        except Exception as e:
            logger.error(f"Error processing file: {e}")
            return False, str(e)

        finally:
            if self.driver:
                self.driver.quit()
                logger.info("Chrome driver closed")


def main():
    """Main function for command-line usage"""
    import sys

    if len(sys.argv) != 3:
        print("Usage: python maps_extractor.py <input_file> <output_file>")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    extractor = GoogleMapsExtractor()
    success, result = extractor.process_file(input_file, output_file)

    if success:
        print(f"\n Success! Output saved to: {output_file}")
    else:
        print(f"\n Error: {result}")


if __name__ == "__main__":
    main()
