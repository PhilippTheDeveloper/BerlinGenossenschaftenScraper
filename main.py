MAIN_PY = """
#!/usr/bin/env python3
\"\"\"
Main entry point for Berlin Housing Scraper - Railway/Nixpacks compatible.
\"\"\"

import os
import sys
import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Optional
import argparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the scraper components
try:
    from src.scraper import BerlinHousingScraper, SearchParameters
    from src.search_interface import ApartmentSearchInterface
except ImportError:
    # Fallback if src directory doesn't exist yet
    logger.warning("Scraper modules not found, using mock implementation")
    
    class SearchParameters:
        def __init__(self, **kwargs):
            self.min_rooms = kwargs.get('min_rooms', 2)
            self.max_rooms = kwargs.get('max_rooms', 3)
            self.max_rent = kwargs.get('max_rent', 1200)
            self.districts = kwargs.get('districts', ['Mitte'])
    
    class ApartmentSearchInterface:
        def search_apartments(self, **kwargs):
            return []


class BerlinHousingApp:
    \"\"\"Main application class for Berlin Housing Scraper.\"\"\"
    
    def __init__(self):
        self.interface = ApartmentSearchInterface()
        self.load_config()
    
    def load_config(self):
        \"\"\"Load configuration from environment variables.\"\"\"
        self.config = {
            'max_rent': float(os.getenv('MAX_RENT', '1200')),
            'min_rooms': float(os.getenv('MIN_ROOMS', '2')),
            'max_rooms': float(os.getenv('MAX_ROOMS', '3')),
            'min_area': float(os.getenv('MIN_AREA', '0')) if os.getenv('MIN_AREA') else None,
            'districts': os.getenv('DISTRICTS', 'Mitte,Friedrichshain').split(','),
            'wbs': os.getenv('WBS_REQUIRED', 'false').lower() == 'true',
            'companies': os.getenv('COMPANIES', 'inberlinwohnen').split(','),
            'port': int(os.getenv('PORT', '8080')),
            'mode': os.getenv('MODE', 'web')
        }
        logger.info(f"Configuration loaded: {self.config}")
    
    def search(self) -> List[Dict]:
        \"\"\"Perform apartment search.\"\"\"
        logger.info("Starting apartment search...")
        
        try:
            results = self.interface.search_apartments(
                min_rooms=self.config['min_rooms'],
                max_rooms=self.config['max_rooms'],
                max_rent=self.config['max_rent'],
                min_area=self.config['min_area'],
                districts=self.config['districts'],
                wbs=self.config['wbs'],
                companies=self.config['companies']
            )
            
            logger.info(f"Found {len(results)} apartments")
            
            # Save results
            self.save_results(results)
            
            return results
            
        except Exception as e:
            logger.error(f"Error during search: {e}")
            return []
    
    def save_results(self, results: List[Dict]):
        \"\"\"Save search results to file.\"\"\"
        os.makedirs('results', exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'results/apartments_{timestamp}.json'
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to {filename}")
        
        # Also save latest results for web display
        with open('results/latest.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    
    def run_web(self):
        \"\"\"Run as web server.\"\"\"
        from flask import Flask, jsonify, request, render_template_string
        from flask_cors import CORS
        
        app = Flask(__name__)
        CORS(app)
        
        @app.route('/')
        def index():
            return self.get_dashboard_html()
        
        @app.route('/health')
        def health():
            return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})
        
        @app.route('/api/search')
        def api_search():
            # Get parameters from query string
            max_rent = request.args.get('max_rent', self.config['max_rent'], type=float)
            min_rooms = request.args.get('min_rooms', self.config['min_rooms'], type=float)
            
            # Override config temporarily
            original_config = self.config.copy()
            self.config['max_rent'] = max_rent
            self.config['min_rooms'] = min_rooms
            
            results = self.search()
            
            # Restore config
            self.config = original_config
            
            return jsonify(results)
        
        @app.route('/api/latest')
        def api_latest():
            try:
                with open('results/latest.json', 'r') as f:
                    return jsonify(json.load(f))
            except FileNotFoundError:
                return jsonify([])
        
        port = self.config['port']
        logger.info(f"Starting web server on port {port}")
        app.run(host='0.0.0.0', port=port)
    
    def run_worker(self):
        \"\"\"Run as background worker.\"\"\"
        logger.info("Starting worker mode...")
        
        while True:
            try:
                self.search()
                # Sleep for 2 hours
                time.sleep(7200)
            except KeyboardInterrupt:
                logger.info("Worker stopped")
                break
            except Exception as e:
                logger.error(f"Worker error: {e}")
                time.sleep(300)  # Sleep 5 minutes on error
    
    def run_scheduler(self):
        \"\"\"Run as scheduler.\"\"\"
        import schedule
        
        logger.info("Starting scheduler mode...")
        
        # Schedule searches
        schedule.every(2).hours.do(self.search)
        schedule.every().day.at("09:00").do(self.search)
        schedule.every().day.at("15:00").do(self.search)
        schedule.every().day.at("21:00").do(self.search)
        
        logger.info("Scheduler configured: Every 2 hours + fixed times at 9:00, 15:00, 21:00")
        
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)
            except KeyboardInterrupt:
                logger.info("Scheduler stopped")
                break
    
    def run_once(self):
        \"\"\"Run search once and exit.\"\"\"
        logger.info("Running single search...")
        results = self.search()
        print(f"\\nFound {len(results)} apartments\\n")
        
        if results:
            print("Top 5 results:")
            print("-" * 80)
            for i, apt in enumerate(results[:5], 1):
                print(f"{i}. {apt.get('title', 'No title')}")
                print(f"   District: {apt.get('district', 'Unknown')}")
                print(f"   Rooms: {apt.get('rooms', 0)}, Area: {apt.get('area', 0)} m²")
                print(f"   Rent: {apt.get('warm_rent', 0)}€ warm")
                print(f"   Available: {apt.get('available_from', 'Unknown')}")
                print()
    
    def get_dashboard_html(self):
        \"\"\"Generate dashboard HTML.\"\"\"
        return '''
<!DOCTYPE html>
<html>
<head>
    <title>Berlin Housing Scraper</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        .header {
            background: white;
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
        }
        .subtitle {
            color: #666;
            font-size: 18px;
        }
        .search-box {
            background: white;
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }
        .search-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .form-group {
            display: flex;
            flex-direction: column;
        }
        label {
            color: #666;
            margin-bottom: 5px;
            font-size: 14px;
        }
        input, select {
            padding: 10px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 16px;
        }
        input:focus, select:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 10px;
            font-size: 18px;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
        }
        .results {
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }
        .apartment {
            border-bottom: 1px solid #e0e0e0;
            padding: 20px 0;
        }
        .apartment:last-child {
            border-bottom: none;
        }
        .apartment-title {
            font-size: 20px;
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
        }
        .apartment-details {
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            color: #666;
        }
        .detail {
            display: flex;
            align-items: center;
            gap: 5px;
        }
        .price {
            color: #667eea;
            font-weight: bold;
            font-size: 18px;
        }
        .loading {
            text-align: center;
            padding: 40px;
            display: none;
        }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 0 auto 20px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        .stat-value {
            font-size: 32px;
            font-weight: bold;
            color: #667eea;
        }
        .stat-label {
            color: #666;
            margin-top: 5px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🏠 Berlin Housing Scraper</h1>
            <p class="subtitle">Find apartments from Berlin's public housing companies</p>
        </div>
        
        <div class="search-box">
            <div class="search-grid">
                <div class="form-group">
                    <label>Max Rent (€)</label>
                    <input type="number" id="maxRent" value="1200">
                </div>
                <div class="form-group">
                    <label>Min Rooms</label>
                    <input type="number" id="minRooms" value="2" step="0.5">
                </div>
                <div class="form-group">
                    <label>Max Rooms</label>
                    <input type="number" id="maxRooms" value="3" step="0.5">
                </div>
                <div class="form-group">
                    <label>Min Area (m²)</label>
                    <input type="number" id="minArea" value="50">
                </div>
            </div>
            <button class="btn" onclick="searchApartments()">🔍 Search Apartments</button>
        </div>
        
        <div class="stats" id="stats" style="display:none;">
            <div class="stat">
                <div class="stat-value" id="totalCount">0</div>
                <div class="stat-label">Total Found</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="avgRent">0</div>
                <div class="stat-label">Avg. Rent (€)</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="wbsCount">0</div>
                <div class="stat-label">With WBS</div>
            </div>
            <div class="stat">
                <div class="stat-value" id="availableNow">0</div>
                <div class="stat-label">Available Now</div>
            </div>
        </div>
        
        <div class="results">
            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>Searching apartments...</p>
            </div>
            <div id="results">
                <p style="text-align: center; color: #666; padding: 40px;">
                    Click "Search Apartments" to start searching
                </p>
            </div>
        </div>
    </div>
    
    <script>
        async function searchApartments() {
            const maxRent = document.getElementById('maxRent').value;
            const minRooms = document.getElementById('minRooms').value;
            const maxRooms = document.getElementById('maxRooms').value;
            const minArea = document.getElementById('minArea').value;
            
            document.getElementById('loading').style.display = 'block';
            document.getElementById('results').innerHTML = '';
            document.getElementById('stats').style.display = 'none';
            
            try {
                const response = await fetch(`/api/search?max_rent=${maxRent}&min_rooms=${minRooms}`);
                const apartments = await response.json();
                
                displayResults(apartments);
                displayStats(apartments);
            } catch (error) {
                document.getElementById('results').innerHTML = '<p style="color: red;">Error loading apartments</p>';
            } finally {
                document.getElementById('loading').style.display = 'none';
            }
        }
        
        function displayResults(apartments) {
            const resultsDiv = document.getElementById('results');
            
            if (apartments.length === 0) {
                resultsDiv.innerHTML = '<p style="text-align: center; color: #666; padding: 40px;">No apartments found</p>';
                return;
            }
            
            resultsDiv.innerHTML = apartments.map(apt => `
                <div class="apartment">
                    <div class="apartment-title">${apt.title || 'Apartment'}</div>
                    <div class="apartment-details">
                        <div class="detail">📍 ${apt.district || 'Unknown'}</div>
                        <div class="detail">🏠 ${apt.rooms || 0} rooms</div>
                        <div class="detail">📐 ${apt.area || 0} m²</div>
                        <div class="detail price">💰 ${apt.warm_rent || 0}€</div>
                        <div class="detail">📅 ${apt.available_from || 'Unknown'}</div>
                        ${apt.wbs_required ? '<div class="detail">🔑 WBS required</div>' : ''}
                    </div>
                    ${apt.url ? `<a href="${apt.url}" target="_blank" style="color: #667eea; text-decoration: none;">View listing →</a>` : ''}
                </div>
            `).join('');
        }
        
        function displayStats(apartments) {
            if (apartments.length === 0) return;
            
            document.getElementById('stats').style.display = 'grid';
            document.getElementById('totalCount').textContent = apartments.length;
            
            const avgRent = Math.round(apartments.reduce((sum, apt) => sum + (apt.warm_rent || 0), 0) / apartments.length);
            document.getElementById('avgRent').textContent = avgRent;
            
            const wbsCount = apartments.filter(apt => apt.wbs_required).length;
            document.getElementById('wbsCount').textContent = wbsCount;
            
            const availableNow = apartments.filter(apt => apt.available_from === 'sofort' || apt.available_from === 'ab sofort').length;
            document.getElementById('availableNow').textContent = availableNow;
        }
        
        // Load latest results on page load
        window.addEventListener('load', async () => {
            try {
                const response = await fetch('/api/latest');
                const apartments = await response.json();
                if (apartments.length > 0) {
                    displayResults(apartments);
                    displayStats(apartments);
                }
            } catch (error) {
                console.error('Error loading latest results:', error);
            }
        });
    </script>
</body>
</html>
        '''
    
    def run(self, mode: Optional[str] = None):
        \"\"\"Run the application in specified mode.\"\"\"
        mode = mode or self.config['mode']
        
        logger.info(f"Starting Berlin Housing Scraper in {mode} mode")
        
        if mode == 'web':
            self.run_web()
        elif mode == 'worker':
            self.run_worker()
        elif mode == 'scheduler':
            self.run_scheduler()
        elif mode == 'once':
            self.run_once()
        else:
            # Default to web mode for Railway
            self.run_web()


def main():
    \"\"\"Main entry point.\"\"\"
    parser = argparse.ArgumentParser(description='Berlin Housing Scraper')
    parser.add_argument('--mode', choices=['web', 'worker', 'scheduler', 'once'], 
                        default=os.getenv('MODE', 'web'),
                        help='Running mode')
    parser.add_argument('--port', type=int, default=int(os.getenv('PORT', '8080')),
                        help='Port for web server')
    
    args = parser.parse_args()
    
    # Set environment variable for port
    os.environ['PORT'] = str(args.port)
    
    app = BerlinHousingApp()
    app.run(mode=args.mode)


if __name__ == '__main__':
    main()
"""