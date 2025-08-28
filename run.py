RUN_PY = """
#!/usr/bin/env python3
\"\"\"
Main entry point for the Berlin Housing Scraper.
\"\"\"

import os
import sys
import json
import time
import click
import logging
import schedule
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Optional

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from scraper import BerlinHousingScraper, SearchParameters
from search_interface import ApartmentSearchInterface
from notifications import NotificationManager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.getenv('LOG_FILE', 'scraper.log')),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def load_search_params() -> SearchParameters:
    \"\"\"Load search parameters from environment variables.\"\"\"
    districts = os.getenv('DISTRICTS', 'Mitte,Friedrichshain').split(',')
    companies = os.getenv('COMPANIES', 'inberlinwohnen').split(',')
    
    return SearchParameters(
        min_rooms=float(os.getenv('MIN_ROOMS', 2)),
        max_rooms=float(os.getenv('MAX_ROOMS', 3)),
        max_rent=float(os.getenv('MAX_RENT', 1200)),
        min_area=float(os.getenv('MIN_AREA', 0)) if os.getenv('MIN_AREA') else None,
        districts=[d.strip() for d in districts],
        wbs_required=os.getenv('WBS_REQUIRED', 'false').lower() == 'true',
        wbs_type=os.getenv('WBS_TYPE'),
        companies=[c.strip() for c in companies]
    )


def search_apartments(notify: bool = True) -> List[dict]:
    \"\"\"Run apartment search with current parameters.\"\"\"
    logger.info("Starting apartment search...")
    
    interface = ApartmentSearchInterface()
    params = load_search_params()
    
    logger.info(f"Search params: {params}")
    
    results = interface.search_apartments(
        min_rooms=params.min_rooms,
        max_rooms=params.max_rooms,
        max_rent=params.max_rent,
        min_area=params.min_area,
        districts=params.districts,
        wbs=params.wbs_required,
        companies=params.companies
    )
    
    logger.info(f"Found {len(results)} apartments")
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    results_dir = 'results'
    os.makedirs(results_dir, exist_ok=True)
    
    # Save JSON
    json_file = os.path.join(results_dir, f'apartments_{timestamp}.json')
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"Results saved to {json_file}")
    
    # Save HTML
    html_file = os.path.join(results_dir, f'apartments_{timestamp}.html')
    html_content = generate_html_report(results)
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    logger.info(f"HTML report saved to {html_file}")
    
    # Send notifications
    if notify and os.getenv('ENABLE_NOTIFICATIONS', 'false').lower() == 'true':
        notifier = NotificationManager()
        notifier.notify(results)
    
    return results


def generate_html_report(apartments: List[dict]) -> str:
    \"\"\"Generate HTML report from apartment data.\"\"\"
    html = \"\"\"
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Berlin Apartment Search Results</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        .stats { background: white; padding: 15px; margin: 20px 0; border-radius: 8px; }
        .apartment { background: white; margin: 10px 0; padding: 15px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .apartment:hover { box-shadow: 0 4px 8px rgba(0,0,0,0.15); }
        .title { font-size: 18px; font-weight: bold; color: #2c3e50; margin-bottom: 10px; }
        .details { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
        .detail { color: #666; }
        .price { color: #e74c3c; font-weight: bold; }
        .wbs { background: #3498db; color: white; padding: 2px 8px; border-radius: 4px; display: inline-block; }
        .available { color: #27ae60; }
        .link { margin-top: 10px; }
        .link a { color: #3498db; text-decoration: none; }
        .link a:hover { text-decoration: underline; }
        .filters { background: white; padding: 15px; margin: 20px 0; border-radius: 8px; }
        .timestamp { color: #999; font-size: 12px; }
    </style>
</head>
<body>
    <h1>🏠 Berlin Apartment Search Results</h1>
    <div class="stats">
        <strong>Found: {count} apartments</strong> | 
        <span class="timestamp">Generated: {timestamp}</span>
    </div>
    
    {apartments_html}
    
    <script>
        // Add filtering functionality
        function filterApartments() {{
            // Implementation here
        }}
    </script>
</body>
</html>
\"\"\"
    
    apartments_html = ""
    for apt in apartments:
        wbs_badge = f'<span class="wbs">WBS {apt.get("wbs_type", "")}</span>' if apt.get('wbs_required') else ''
        apartments_html += f\"\"\"
        <div class="apartment">
            <div class="title">{apt.get('title', 'No title')}</div>
            <div class="details">
                <div class="detail">📍 {apt.get('district', 'Unknown')}</div>
                <div class="detail">🏠 {apt.get('rooms', 0)} Zimmer, {apt.get('area', 0)} m²</div>
                <div class="detail price">💰 {apt.get('warm_rent', 0)}€ warm</div>
                <div class="detail available">📅 {apt.get('available_from', 'sofort')}</div>
            </div>
            <div>{wbs_badge}</div>
            <div class="link">
                <a href="{apt.get('url', '#')}" target="_blank">View Listing →</a>
            </div>
        </div>
        \"\"\"
    
    return html.format(
        count=len(apartments),
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        apartments_html=apartments_html
    )


def run_scheduler():
    \"\"\"Run the scheduler for periodic searches.\"\"\"
    logger.info("Starting scheduler...")
    
    interval = int(os.getenv('SCHEDULE_INTERVAL', 2))
    start_hour = int(os.getenv('SCHEDULE_START_HOUR', 8))
    end_hour = int(os.getenv('SCHEDULE_END_HOUR', 22))
    
    # Schedule searches every N hours between start and end hours
    for hour in range(start_hour, end_hour, interval):
        schedule.every().day.at(f"{hour:02d}:00").do(search_apartments)
    
    logger.info(f"Scheduled searches every {interval} hours from {start_hour}:00 to {end_hour}:00")
    
    while True:
        schedule.run_pending()
        time.sleep(60)


@click.command()
@click.option('--action', type=click.Choice(['search', 'schedule', 'web', 'generate-static']), 
              default='search', help='Action to perform')
@click.option('--max-rent', type=float, help='Maximum rent')
@click.option('--min-rooms', type=float, help='Minimum rooms')
@click.option('--districts', help='Comma-separated list of districts')
@click.option('--notify', type=str, help='Notification methods (telegram,email,discord)')
@click.option('--port', type=int, default=5000, help='Port for web server')
def main(action, max_rent, min_rooms, districts, notify, port):
    \"\"\"Berlin Housing Scraper CLI.\"\"\"
    
    # Override environment variables with CLI arguments
    if max_rent:
        os.environ['MAX_RENT'] = str(max_rent)
    if min_rooms:
        os.environ['MIN_ROOMS'] = str(min_rooms)
    if districts:
        os.environ['DISTRICTS'] = districts
    
    if action == 'search':
        results = search_apartments(notify=bool(notify))
        print(f"Found {len(results)} apartments")
        
    elif action == 'schedule':
        run_scheduler()
        
    elif action == 'web':
        from flask_app import app
        app.run(host='0.0.0.0', port=port)
        
    elif action == 'generate-static':
        results = search_apartments(notify=False)
        # Generate static site for deployment
        os.makedirs('dist', exist_ok=True)
        with open('dist/index.html', 'w') as f:
            f.write(generate_html_report(results))
        print("Static site generated in dist/")


if __name__ == '__main__':
    main()
"""
