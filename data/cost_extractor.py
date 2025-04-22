import re
from bs4 import BeautifulSoup

class CostExtractor:
    def __init__(self, cpt_codes, logger=None):
        """
        Initialize the cost extractor.
        
        Args:
            cpt_codes (list): List of CPT codes to look for
            logger: Logger object for logging information
        """
        # Store the CPT codes as provided
        self.cpt_codes = cpt_codes
        self.logger = logger
        
        # Regular expressions for price/cost extraction
        self.price_patterns = [
            r'\$\s*[\d,]+\.?\d*',  # $1,234.56
            r'cost[s]?\s*(?:of|is|are|:)?\s*\$\s*[\d,]+\.?\d*',  # cost: $1,234
            r'price[s]?\s*(?:of|is|are|:)?\s*\$\s*[\d,]+\.?\d*',  # price: $1,234
            r'charge[s]?\s*(?:of|is|are|:)?\s*\$\s*[\d,]+\.?\d*',  # charge: $1,234
            r'fee[s]?\s*(?:of|is|are|:)?\s*\$\s*[\d,]+\.?\d*',  # fee: $1,234
        ]
        
        # Additional patterns for finding CPT codes in context
        self.cpt_context_patterns = [
            r'(?:CPT|cpt)[\s:]*(\d{5})',  # CPT: 12345
            r'(?:code|procedure)[\s:]*(\d{5})',  # code: 12345
            r'(\d{5})[\s:]*(?:procedure|code)',  # 12345 procedure
        ]
    
    def find_costs_near_cpt(self, text, cpt_code, url):
        """
        Find costs that appear near a specific CPT code.
        
        Args:
            text (str): Text to search in
            cpt_code (str): CPT code to look for
            url (str): URL being processed (for logging)
            
        Returns:
            list: List of found prices
        """
        # Look for the CPT code
        cpt_positions = [m.start() for m in re.finditer(re.escape(cpt_code), text)]
        
        if not cpt_positions:
            return []
            
        prices = []
        
        # For each CPT code occurrence
        for pos in cpt_positions:
            # Extract a window around the CPT code (300 chars before and after - wider window)
            window_start = max(0, pos - 300)
            window_end = min(len(text), pos + 300)
            window = text[window_start:window_end]
            
            # Look for prices in this window
            for pattern in self.price_patterns:
                price_matches = re.finditer(pattern, window, re.IGNORECASE)
                for match in price_matches:
                    # Extract just the dollar amount
                    price_str = match.group(0)
                    price_value = re.search(r'\$\s*([\d,]+\.?\d*)', price_str)
                    if price_value:
                        # Remove commas and convert to float
                        try:
                            price = float(price_value.group(1).replace(',', ''))
                            prices.append(price)
                            
                            if self.logger:
                                context = window[max(0, match.start() - 50):min(len(window), match.end() + 50)]
                                self.logger.data_logger.info(f"  Found price ${price} near CPT {cpt_code} in context: '...{context}...'")
                        except ValueError:
                            if self.logger:
                                self.logger.log_error(url, f"Could not parse price from {price_str}")
        
        return prices
        
    def extract_costs(self, soup, url):
        """
        Extract healthcare costs from a page.
        
        Args:
            soup (BeautifulSoup): Parsed HTML content
            url (str): URL of the current page
            
        Returns:
            dict: Extracted cost information
        """
        results = {}
        
        # Convert the page to text
        text = soup.get_text()
        
        # Look for each CPT code
        for cpt_code in self.cpt_codes:
            # Check if the CPT code is on the page
            if cpt_code in text:
                prices = self.find_costs_near_cpt(text, cpt_code, url)
                
                if prices:
                    results[cpt_code] = {
                        'prices': prices,
                        'min_price': min(prices) if prices else None,
                        'max_price': max(prices) if prices else None,
                        'avg_price': sum(prices) / len(prices) if prices else None
                    }
                    
                    if self.logger:
                        self.logger.data_logger.info(f"  Summary for CPT {cpt_code}: {len(prices)} prices found, "
                                                   f"min=${min(prices):.2f}, max=${max(prices):.2f}, avg=${sum(prices)/len(prices):.2f}")
        
        # Try to find costs in tables - tables often contain pricing information
        tables = soup.find_all('table')
        for table_idx, table in enumerate(tables):
            # Check each row in the table
            rows = table.find_all('tr')
            
            for row_idx, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                row_text = ' '.join(cell.get_text().strip() for cell in cells)
                
                # Look for each CPT code in this row
                for cpt_code in self.cpt_codes:
                    if cpt_code in row_text:
                        if self.logger:
                            self.logger.data_logger.info(f"  Found CPT {cpt_code} in table #{table_idx+1}, row #{row_idx+1}")
                        
                        # Look for prices in this row
                        for pattern in self.price_patterns:
                            price_match = re.search(pattern, row_text, re.IGNORECASE)
                            if price_match:
                                price_str = price_match.group(0)
                                price_value = re.search(r'\$\s*([\d,]+\.?\d*)', price_str)
                                if price_value:
                                    try:
                                        price = float(price_value.group(1).replace(',', ''))
                                        if self.logger:
                                            self.logger.data_logger.info(f"  Found price ${price} for CPT {cpt_code} in table")
                                            
                                        if cpt_code not in results:
                                            results[cpt_code] = {
                                                'prices': [price],
                                                'min_price': price,
                                                'max_price': price,
                                                'avg_price': price
                                            }
                                        else:
                                            results[cpt_code]['prices'].append(price)
                                            results[cpt_code]['min_price'] = min(results[cpt_code]['prices'])
                                            results[cpt_code]['max_price'] = max(results[cpt_code]['prices'])
                                            results[cpt_code]['avg_price'] = sum(results[cpt_code]['prices']) / len(results[cpt_code]['prices'])
                                    except ValueError:
                                        if self.logger:
                                            self.logger.log_error(url, f"Could not parse price from {price_str} in table")
        
        # Look for prices in common structured formats (e.g., HTML table with price lists)
        self._extract_from_price_lists(soup, results, url)
        
        return results
    
    def _extract_from_price_lists(self, soup, results, url):
        """Extract costs from structured price lists"""
        # Look for tables with headers like "CPT Code", "Price", "Cost", etc.
        tables = soup.find_all('table')
        
        for table in tables:
            # Find headers to determine columns
            headers = table.find_all('th')
            headers_text = [h.get_text().lower().strip() for h in headers]
            
            # Try to identify CPT code and price columns
            cpt_col = None
            price_col = None
            
            for i, header in enumerate(headers_text):
                if any(term in header for term in ['cpt', 'code', 'procedure']):
                    cpt_col = i
                if any(term in header for term in ['price', 'cost', 'fee', 'charge', '$']):
                    price_col = i
            
            # If we identified both columns, extract the data
            if cpt_col is not None and price_col is not None:
                rows = table.find_all('tr')
                
                for row in rows[1:]:  # Skip header row
                    cells = row.find_all(['td', 'th'])
                    if len(cells) > max(cpt_col, price_col):
                        cpt_cell = cells[cpt_col].get_text().strip()
                        price_cell = cells[price_col].get_text().strip()
                        
                        # Check if this cell contains any of our CPT codes
                        for cpt_code in self.cpt_codes:
                            if cpt_code in cpt_cell:
                                # Extract price
                                price_match = re.search(r'\$?\s*([\d,]+\.?\d*)', price_cell)
                                if price_match:
                                    try:
                                        price = float(price_match.group(1).replace(',', ''))
                                        if self.logger:
                                            self.logger.data_logger.info(f"  Found price ${price} for CPT {cpt_code} in structured table")
                                            
                                        if cpt_code not in results:
                                            results[cpt_code] = {
                                                'prices': [price],
                                                'min_price': price,
                                                'max_price': price,
                                                'avg_price': price
                                            }
                                        else:
                                            results[cpt_code]['prices'].append(price)
                                            results[cpt_code]['min_price'] = min(results[cpt_code]['prices'])
                                            results[cpt_code]['max_price'] = max(results[cpt_code]['prices'])
                                            results[cpt_code]['avg_price'] = sum(results[cpt_code]['prices']) / len(results[cpt_code]['prices'])
                                    except ValueError:
                                        pass