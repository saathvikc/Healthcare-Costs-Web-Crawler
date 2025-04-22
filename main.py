import argparse
import sys
import os
import subprocess
import pkg_resources

def check_and_install_requirements():
    """Check if required packages are installed, and install them if necessary"""
    # Path to requirements file
    requirements_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'requirements.txt')
    
    if not os.path.exists(requirements_file):
        print("Warning: requirements.txt not found")
        return
        
    # Read required packages
    with open(requirements_file, 'r') as f:
        requirements = [line.strip() for line in f.readlines() if not line.strip().startswith('//')]
    
    # Get installed packages
    installed = {pkg.key for pkg in pkg_resources.working_set}
    missing = []
    
    for requirement in requirements:
        # Skip empty lines
        if not requirement:
            continue
            
        # Parse package name (remove version specifiers)
        package_name = requirement.split('>=')[0].split('==')[0].split('>')[0].strip()
        
        if package_name.lower() not in installed:
            missing.append(requirement)
    
    # Install missing packages
    if missing:
        print(f"Installing {len(missing)} missing packages...")
        subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + missing)
        print("All required packages installed successfully.")

# Import project modules after ensuring requirements are installed
def import_modules():
    """Import project modules"""
    global WebCrawler, PageParser, CostExtractor, ResultsDatabase, DistanceCalculator, HospitalFinder, Logger
    
    from crawler.web_crawler import WebCrawler
    from crawler.page_parser import PageParser
    from data.cost_extractor import CostExtractor
    from data.database import ResultsDatabase
    from utils.hospital_finder import HospitalFinder
    from utils.logger import Logger

# Update the parse_args function

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Healthcare Cost Finder')
    
    parser.add_argument('--cpt', nargs='+', required=True, help='CPT codes to search for')
    parser.add_argument('--city', required=True, help='US city name')
    parser.add_argument('--state', help='State abbreviation (e.g., CA, NY)')
    parser.add_argument('--limit', type=int, default=25, help='Maximum number of hospitals to search')
    parser.add_argument('--max-depth', type=int, default=3, help='Maximum crawl depth')
    parser.add_argument('--max-pages', type=int, default=100, help='Maximum pages to crawl')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between requests in seconds')
    parser.add_argument('--output', default='results.json', help='Output file for results')
    # Use an absolute path to the logs directory by default
    default_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    parser.add_argument('--log-dir', default=default_log_dir, help='Directory for log files')
    
    return parser.parse_args()

# Update the main function to use city instead of location
def main():
    """Main entry point"""
    # Check and install required packages first
    check_and_install_requirements()
    
    # Import modules after installing requirements
    import_modules()
    
    args = parse_args()
    
    # Format location for display
    location = args.city
    if args.state:
        location = f"{args.city}, {args.state}"
    
    # We require CPT codes to be provided directly
    cpt_codes = args.cpt
    print(f"Searching for {len(cpt_codes)} CPT codes: {', '.join(cpt_codes)}")
    
    # Initialize logger with CPT codes and location
    logger = Logger(log_dir=args.log_dir, cpt_codes=cpt_codes, location=location)
    
    # Create the hospital finder
    hospital_finder = HospitalFinder()
    
    print(f"Finding up to {args.limit} hospitals in {location}...")
    seed_urls = hospital_finder.get_hospital_seed_urls(args.city, args.state, limit=args.limit)
    
    if not seed_urls:
        print("No hospital websites found in this city. Please try a different city.")
        sys.exit(1)
    
    # Log the list of hospitals that will be checked
    hospitals_list = []
    for url, hospital in seed_urls.items():
        if hospital not in hospitals_list:
            hospitals_list.append(hospital)
    
    # Log unique hospitals
    logger.log_hospitals_list(hospitals_list)
        
    print(f"Found {len(seed_urls)} seed URLs from {len(hospitals_list)} hospitals in {location}")
    
    # Create the page parser with healthcare keywords
    healthcare_keywords = [
        'price', 'cost', 'fee', 'charge', 'pricing',
        'estimate', 'hospital', 'clinic', 'medical', 'healthcare',
        'procedure', 'surgery', 'diagnostic', 'treatment', 'cpt',
        'insurance', 'price-transparency', 'cash-price',
        'patient-cost', 'billing', 'financial', 'payment'
    ]
    page_parser = PageParser(keywords=healthcare_keywords)
    
    # Create the cost extractor with more aggressive price detection
    cost_extractor = CostExtractor(cpt_codes, logger=logger)
    
    # Create and run the web crawler
    crawler = WebCrawler(
        seed_urls=seed_urls,
        hospital_info=seed_urls,  # Pass the hospital info
        max_depth=args.max_depth,
        delay=args.delay,
        max_pages=args.max_pages,
        logger=logger
    )
    
    print("Starting web crawler...")
    results = crawler.crawl(page_parser, cost_extractor)
    print(f"Crawling complete - found cost information on {len(results)} pages")
    
    # No need for distance calculations - we're only working within a single city
    # All hospitals are assumed to be in the specified city
    
    # Store results in database
    db = ResultsDatabase(args.output)
    search_id = db.store_results(results, location, cpt_codes)
    print(f"Results saved with search ID: {search_id}")
    
    # Log search completion
    logger.log_search_complete(len(results), search_id)
    
    # Print best prices for each CPT code
    best_prices = {}
    print("\nBest prices found:")
    for cpt_code in cpt_codes:
        best = db.find_best_price(cpt_code)
        best_prices[cpt_code] = best
        if best:
            hospital_name = best['hospital_info'].get('name', 'Unknown Hospital')
            print(f"CPT {cpt_code}: ${best['price']:.2f} at {hospital_name}")
        else:
            print(f"CPT {cpt_code}: No prices found")
    
    # Log best prices
    logger.log_best_prices(best_prices)
    
    # Get the search directory for output
    search_dir = logger.get_search_dir()
    print(f"\nDetailed logs saved in {search_dir}/")

if __name__ == "__main__":
    main()