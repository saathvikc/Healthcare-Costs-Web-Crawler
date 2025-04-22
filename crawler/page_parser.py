from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import re

class PageParser:
    def __init__(self, keywords=None):
        """
        Initialize the page parser.
        
        Args:
            keywords (list): Keywords to look for when deciding if a link is relevant
        """
        self.keywords = keywords or []
        
    def extract_links(self, soup, base_url):
        """
        Extract links from the page and filter for relevant ones.
        
        Args:
            soup (BeautifulSoup): Parsed HTML content
            base_url (str): URL of the current page for resolving relative links
            
        Returns:
            list: List of absolute URLs found on the page
        """
        links = []
        
        # Find all links
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            
            # Skip fragment links and javascript
            if href.startswith('#') or href.startswith('javascript:'):
                continue
                
            # Convert to absolute URL
            absolute_url = urljoin(base_url, href)
            
            # Make sure it's HTTP or HTTPS
            if not absolute_url.startswith(('http://', 'https://')):
                continue
                
            # Check if we should stay on same domain
            base_domain = urlparse(base_url).netloc
            link_domain = urlparse(absolute_url).netloc
            
            # Add more sophisticated filtering here if needed
            # For now, we accept links from the same domain and those that contain keywords
            if (base_domain == link_domain or
                any(keyword.lower() in absolute_url.lower() for keyword in self.keywords)):
                links.append(absolute_url)
                
        return links
        
    def get_text_from_element(self, element):
        """Extract clean text from an element."""
        if element:
            return ' '.join(element.get_text(separator=' ').split())
        return ""
        
    def find_hospital_info(self, soup, url):
        """
        Try to find hospital information from the page.
        
        Args:
            soup (BeautifulSoup): Parsed HTML content
            url (str): URL of the current page
            
        Returns:
            dict: Hospital information
        """
        hospital_info = {
            'name': None,
            'address': None,
            'phone': None
        }
        
        # Try to find hospital name - often in title, heading, or meta tags
        title_tag = soup.find('title')
        if title_tag:
            hospital_info['name'] = self.get_text_from_element(title_tag)
        
        # Try common schemas
        org_schema = soup.find('div', {'itemtype': 'http://schema.org/Organization'})
        if org_schema:
            name_elem = org_schema.find('meta', {'itemprop': 'name'}) or org_schema.find('span', {'itemprop': 'name'})
            if name_elem and 'content' in name_elem.attrs:
                hospital_info['name'] = name_elem['content']
            elif name_elem:
                hospital_info['name'] = self.get_text_from_element(name_elem)
                
            address_elem = org_schema.find('div', {'itemprop': 'address'})
            if address_elem:
                hospital_info['address'] = self.get_text_from_element(address_elem)
                
            phone_elem = org_schema.find('span', {'itemprop': 'telephone'})
            if phone_elem:
                hospital_info['phone'] = self.get_text_from_element(phone_elem)
        
        # Try to find address using regex patterns
        if not hospital_info['address']:
            # Look for address patterns in text
            address_pattern = r'\b\d+\s+[A-Za-z0-9\s,\.]+\b(Road|Rd|Street|St|Avenue|Ave|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Way)\b'
            text = soup.get_text()
            address_match = re.search(address_pattern, text, re.IGNORECASE)
            if address_match:
                hospital_info['address'] = address_match.group(0)
        
        # Try to find phone using regex patterns
        if not hospital_info['phone']:
            phone_pattern = r'\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}'
            phone_matches = re.findall(phone_pattern, soup.get_text())
            if phone_matches:
                hospital_info['phone'] = phone_matches[0]
        
        return hospital_info