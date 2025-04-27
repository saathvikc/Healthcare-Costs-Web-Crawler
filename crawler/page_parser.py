import requests
import pandas as pd
from bs4 import BeautifulSoup
from typing import Dict, Any, Optional
import re
import io
import json
import csv

class CostInfoParser:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
    
    def parse_cost_file(self, file_url: str, file_type: str, cpt_code: str) -> Optional[Dict[str, Any]]:
        """
        Parse structured files (CSV, Excel, JSON) for cost information.
        
        Args:
            file_url: URL to the file
            file_type: Type of file ('csv', 'xlsx', 'json', etc.)
            cpt_code: CPT code to search for
            
        Returns:
            Dictionary with cost information or None if not found
        """
        try:
            response = requests.get(file_url, headers=self.headers, timeout=15)
            if response.status_code != 200:
                return None
                
            if file_type.lower() in ['csv']:
                return self._parse_csv(response.content, cpt_code)
            elif file_type.lower() in ['xlsx', 'xls']:
                return self._parse_excel(response.content, cpt_code)
            elif file_type.lower() == 'json':
                return self._parse_json(response.content, cpt_code)
            elif file_type.lower() == 'xml':
                return self._parse_xml(response.content, cpt_code)
            else:
                return None
        
        except Exception as e:
            print(f"Error parsing {file_url}: {e}")
            return None
    
    def _parse_csv(self, content: bytes, cpt_code: str) -> Optional[Dict[str, Any]]:
        """Parse CSV file for cost information"""
        try:
            # Try different encodings
            for encoding in ['utf-8', 'latin-1', 'cp1252']:
                try:
                    df = pd.read_csv(io.BytesIO(content), encoding=encoding, error_bad_lines=False)
                    break
                except:
                    continue
            else:
                # If all encodings fail, try to read it as a string and manually parse
                csv_text = content.decode('utf-8', errors='ignore')
                reader = csv.reader(csv_text.splitlines())
                rows = list(reader)
                
                for row in rows:
                    row_text = ' '.join(str(cell) for cell in row).lower()
                    if cpt_code in row_text:
                        cost_match = re.search(r'\$([\d,]+(\.\d{2})?)', row_text)
                        if cost_match:
                            return {
                                "status": "found",
                                "cost": cost_match.group(0),
                                "type": "csv_manual"
                            }
                return None
            
            # Check if any column contains the CPT code
            for col in df.columns:
                if df[col].astype(str).str.contains(cpt_code).any():
                    # Find the row with the CPT code
                    matching_rows = df[df[col].astype(str).str.contains(cpt_code)]
                    
                    # Look for columns that might contain price information
                    price_cols = [c for c in df.columns if any(term in str(c).lower() 
                                 for term in ['price', 'cost', 'charge', 'fee', 'amount'])]
                    
                    if price_cols and not matching_rows.empty:
                        for price_col in price_cols:
                            price = matching_rows[price_col].iloc[0]
                            if price and not pd.isna(price):
                                return {
                                    "status": "found",
                                    "cost": f"${price}" if not str(price).startswith('$') else str(price),
                                    "type": "csv"
                                }
            
            # If we couldn't find it using column names, search through all data
            for _, row in df.iterrows():
                row_text = ' '.join(str(cell) for cell in row).lower()
                if cpt_code in row_text:
                    cost_match = re.search(r'\$([\d,]+(\.\d{2})?)', row_text)
                    if cost_match:
                        return {
                            "status": "found",
                            "cost": cost_match.group(0),
                            "type": "csv_row_search"
                        }
            
            return None
            
        except Exception as e:
            print(f"Error parsing CSV: {e}")
            return None
    
    def _parse_excel(self, content: bytes, cpt_code: str) -> Optional[Dict[str, Any]]:
        """Parse Excel file for cost information"""
        try:
            df = pd.read_excel(io.BytesIO(content))
            
            # Similar logic as CSV parsing
            for col in df.columns:
                if df[col].astype(str).str.contains(cpt_code).any():
                    matching_rows = df[df[col].astype(str).str.contains(cpt_code)]
                    
                    price_cols = [c for c in df.columns if any(term in str(c).lower() 
                                 for term in ['price', 'cost', 'charge', 'fee', 'amount'])]
                    
                    if price_cols and not matching_rows.empty:
                        for price_col in price_cols:
                            price = matching_rows[price_col].iloc[0]
                            if price and not pd.isna(price):
                                return {
                                    "status": "found",
                                    "cost": f"${price}" if not str(price).startswith('$') else str(price),
                                    "type": "excel"
                                }
            
            # Search through all data if column method fails
            for _, row in df.iterrows():
                row_text = ' '.join(str(cell) for cell in row).lower()
                if cpt_code in row_text:
                    cost_match = re.search(r'\$([\d,]+(\.\d{2})?)', row_text)
                    if cost_match:
                        return {
                            "status": "found",
                            "cost": cost_match.group(0),
                            "type": "excel_row_search"
                        }
                        
            return None
            
        except Exception as e:
            print(f"Error parsing Excel: {e}")
            return None
    
    def _parse_json(self, content: bytes, cpt_code: str) -> Optional[Dict[str, Any]]:
        """Parse JSON file for cost information"""
        try:
            data = json.loads(content)
            
            # Recursively search through JSON
            result = self._search_json_for_cpt(data, cpt_code)
            return result
            
        except Exception as e:
            print(f"Error parsing JSON: {e}")
            return None
    
    def _search_json_for_cpt(self, data, cpt_code: str) -> Optional[Dict[str, Any]]:
        """Recursively search through JSON structure for CPT code and cost"""
        if isinstance(data, dict):
            # Check if this dictionary contains our CPT code
            str_dict = str(data).lower()
            if cpt_code in str_dict:
                # Look for cost/price keys
                price_keys = [k for k in data.keys() if any(term in str(k).lower() 
                             for term in ['price', 'cost', 'charge', 'fee', 'amount'])]
                
                if price_keys:
                    for key in price_keys:
                        value = data[key]
                        if isinstance(value, (int, float, str)):
                            return {
                                "status": "found",
                                "cost": f"${value}" if not str(value).startswith('$') else str(value),
                                "type": "json"
                            }
                
                # If we found the CPT but not price, look for price pattern
                cost_match = re.search(r'\$([\d,]+(\.\d{2})?)', str_dict)
                if cost_match:
                    return {
                        "status": "found",
                        "cost": cost_match.group(0),
                        "type": "json_regex"
                    }
            
            # Recursively search nested dictionaries
            for key, value in data.items():
                result = self._search_json_for_cpt(value, cpt_code)
                if result:
                    return result
                    
        elif isinstance(data, list):
            # Search through list items
            for item in data:
                result = self._search_json_for_cpt(item, cpt_code)
                if result:
                    return result
        
        return None
    
    def _parse_xml(self, content: bytes, cpt_code: str) -> Optional[Dict[str, Any]]:
        """Parse XML file for cost information"""
        try:
            soup = BeautifulSoup(content, 'xml')
            if soup is None:
                soup = BeautifulSoup(content, 'lxml')
                
            # Convert to string and search
            xml_text = str(soup).lower()
            if cpt_code in xml_text:
                # Find elements that might contain our CPT code
                for tag in soup.find_all():
                    if cpt_code in str(tag).lower():
                        # Look for price elements nearby
                        price_tags = tag.find_all(lambda t: any(term in t.name.lower() 
                                     for term in ['price', 'cost', 'charge', 'fee', 'amount']))
                        
                        if price_tags:
                            for price_tag in price_tags:
                                return {
                                    "status": "found",
                                    "cost": price_tag.text,
                                    "type": "xml"
                                }
                        
                        # If no explicit price tags, look for price pattern
                        tag_text = tag.get_text()
                        cost_match = re.search(r'\$([\d,]+(\.\d{2})?)', tag_text)
                        if cost_match:
                            return {
                                "status": "found",
                                "cost": cost_match.group(0),
                                "type": "xml_regex"
                            }
            
            return None
            
        except Exception as e:
            print(f"Error parsing XML: {e}")
            return None