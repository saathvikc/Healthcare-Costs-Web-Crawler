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
    from utils.distance import DistanceCalculator
    from utils.hospital_finder import HospitalFinder
    from utils.logger import Logger

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(description='Healthcare Cost Finder')
    
    parser.add_argument('--cpt', nargs='+', required=True, help='CPT codes to search for')
    parser.add_argument('--location', required=True, help='Patient location (address)')
    parser.add_argument('--radius', type=float, default=25.0, help='Search radius in miles')
    parser.add_argument('--max-depth', type=int, default=3, help='Maximum crawl depth')
    parser.add_argument('--max-pages', type=int, default=100, help='Maximum pages to crawl')
    parser.add_argument('--delay', type=float, default=1.0, help='Delay between requests in seconds')
    parser.add_argument('--output', default='results.json', help='Output file for results')
    # Use an absolute path to the logs directory by default
    default_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
    parser.add_argument('--log-dir', default=default_log_dir, help='Directory for log files')
    
    return parser.parse_args()

def main():
    """Main entry point"""
    # Check and install required packages first
    check_and_install_requirements()
    
    # Import modules after installing requirements
    import_modules()
    
    args = parse_args()
    
    # Initialize logger
    logger = Logger(log_dir=args.log_dir)
    
    # We require CPT codes to be provided directly
    cpt_codes = args.cpt
    print(f"Searching for {len(cpt_codes)} CPT codes: {', '.join(cpt_codes)}")
    
    # Create the hospital finder
    hospital_finder = HospitalFinder()
    print(f"Finding hospitals within {args.radius} miles of {args.location}...")
    seed_urls = hospital_finder.get_hospital_seed_urls(args.location, args.radius)
    
    if not seed_urls:
        print("No hospital websites found nearby. Please try a different location or increase the radius.")
        sys.exit(1)
        
    print(f"Found {len(seed_urls)} seed URLs from {len(set(hospital['name'] for hospital in seed_urls.values()))} nearby hospitals")
    
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
    
    # Calculate distances to hospitals
    distance_calculator = DistanceCalculator()
    for url, data in results.items():
        if 'hospital_info' in data and data['hospital_info'].get('address'):
            distance = distance_calculator.calculate_distance(
                args.location, data['hospital_info']['address']
            )
            if distance:
                data['hospital_info']['distance'] = round(distance, 2)
    
    # Store results in database
    db = ResultsDatabase(args.output)
    search_id = db.store_results(results, args.location, cpt_codes)
    print(f"Results saved with search ID: {search_id}")
    
    # Print best prices for each CPT code
    print("\nBest prices found:")
    for cpt_code in cpt_codes:
        best = db.find_best_price(cpt_code)
        if best:
            hospital_name = best['hospital_info'].get('name', 'Unknown Hospital')
            distance = best['hospital_info'].get('distance', 'Unknown')
            print(f"CPT {cpt_code}: ${best['price']:.2f} at {hospital_name} "
                  f"(Distance: {distance} miles)")
        else:
            print(f"CPT {cpt_code}: No prices found")
    
    print(f"\nDetailed logs saved in {args.log_dir}/")

if __name__ == "__main__":
    main()