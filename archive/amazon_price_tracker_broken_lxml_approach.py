#!/usr/bin/env python3
"""
Amazon Resale Price Tracker - FINAL VERSION WITH NUCLEAR RESALE DETECTION
Finds "amazon resale" EVEN WHEN in other sellers section
"""

import random
import requests
from bs4 import BeautifulSoup
import logging
import time
import json
import re
from datetime import datetime
from urllib.parse import urljoin

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('amazon_tracker.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# LOAD YOUR 84 ASINs
try:
    with open('amazon_watchlist.txt', 'r') as f:
        asin_list = [line.strip() for line in f if line.strip()]
except:
    asin_list = ['B0CFPJYX7P', 'B0FFTRPM4K']

CONFIG = {
    'asin_list': asin_list,
    'telegram_token': 'YOUR_BOT_TOKEN_HERE',
    'telegram_chat_id': 'YOUR_CHAT_ID_HERE',
    'check_interval': 300,
    'price_history_file': 'price_history.json',
    'user_agents': [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    ]
}

class AmazonTracker:
    def load_price_history(self):
        try:
            with open(CONFIG['price_history_file'], 'r') as f:
                return json.load(f)
        except:
            return {}

    def save_price_history(self):
        with open(CONFIG['price_history_file'], 'w') as f:
            json.dump(self.price_history, f, indent=2)

    def parse_price(self, price_text):
        if not price_text:
            return None
        match = re.search(r'[\d,]+\.?\d*', price_text.replace('$', ''))
        return float(match.group().replace(',', '')) if match else None

    def get_random_ua(self):
        return random.choice(CONFIG['user_agents'])

    def __init__(self):
        self.session = requests.Session()
        self.price_history = self.load_price_history()
        self.session.headers.update({
            'User-Agent': self.get_random_ua(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="131", "Google Chrome";v="131"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Linux"',
        })
        logger.info("🚀 Tracker initialized - Nuclear Amazon Resale detection")

    # def find_amazon_resale_price_nuclear(self, soup):
    #     """🔥 NUCLEAR SEARCH - Finds amazon resale ANYWHERE on page"""
        
    #     # Method 1: Search entire page text first
    #     page_text = soup.get_text().lower()
    #     if 'amazon resale' not in page_text:
    #         return None
        
    #     logger.info("🔍 'amazon resale' text DETECTED on page")
        
    #     # Method 2: Find ALL seller elements
    #     seller_selectors = [
    #         '#sellerProfileTriggerId',
    #         '.sellerName', 
    #         '[data-seller-name]',
    #         '.a-size-base-plus',
    #         '.olpOfferSeller',
    #         '.offerlist_sellername'
    #     ]
        
    #     for selector in seller_selectors:
    #         sellers = soup.select(selector)
    #         for seller in sellers:
    #             if 'amazon resale' in seller.get_text().lower():
    #                 logger.info(f"👤 AMAZON RESALE seller element found!")
                    
    #                 # Find nearest price (within 5 parent/sibling levels)
    #                 current = seller
    #                 for _ in range(10):  # Look up and down
    #                     price_el = current.select_one('span.a-offscreen, .a-price-whole, .a-price-3p-whole')
    #                     if price_el:
    #                         price = self.parse_price(price_el.get_text())
    #                         if price and price > 0:
    #                             logger.info(f"🎯 RESALE PRICE: ${price:.2f}")
    #                             return price
                        
    #                     # Move to parent/sibling
    #                     if current.parent:
    #                         current = current.parent
    #                     elif current.next_sibling:
    #                         current = current.next_sibling
    #                     else:
    #                         break
        
    #     # Method 3: Check offers section specifically
    #     offers_section = soup.select_one('#offers-accordion-container, .olpOffer')
    #     if offers_section:
    #         prices = offers_section.select('.a-price-whole, span.a-offscreen')
    #         for price_el in prices:
    #             price = self.parse_price(price_el.get_text())
    #             if price:
    #                 logger.info(f"🎁 OFFERS SECTION RESALE: ${price:.2f}")
    #                 return price
        
    #     return None

    def find_amazon_resale_price_nuclear(self, soup):
        """💥 ULTIMATE FIX - Parses entire offers section"""
        
        # 1. Check if offers page needed
        if soup.select_one('.olpOffer'):
            logger.info("🔗 Found offers section - parsing ALL sellers")
            
            # Parse ALL offer rows
            offers = soup.select('.olpOffer, .olpOfferContainer')
            for offer in offers:
                seller = offer.select_one('.olpOfferSeller, .sellerName, .a-size-base-plus')
                price_el = offer.select_one('.a-price-whole, span.a-offscreen, .a-price-3p-whole')
                
                if seller and 'amazon resale' in seller.get_text().lower() and price_el:
                    price = self.parse_price(price_el.get_text())
                    if price:
                        logger.info(f"🎯 RESALE OFFER: ${price:.2f}")
                        return price
        
        # 2. Fallback: buybox amazon resale  
        buybox_seller = soup.select_one('#sellerProfileTriggerId')
        if buybox_seller and 'amazon resale' in buybox_seller.get_text().lower():
            price = self.find_any_price(soup)
            if price:
                logger.info(f"🎯 BUYBOX RESALE: ${price:.2f}")
                return price
                
        return None


    def find_any_price(self, soup):
        """Fallback - any buybox price"""
        selectors = [
            '#corePrice_feature_div span.a-offscreen',
            '#priceblock_dealprice',
            'span.a-price-whole',
            '.a-price.aok-align-center span.a-offscreen',
            '.a-price-3p-whole'
        ]
        
        for sel in selectors:
            price_el = soup.select_one(sel)
            if price_el:
                price = self.parse_price(price_el.get_text())
                if price:
                    return price
        return None

    def scrape_product(self, asin):
        url = f"https://www.amazon.com/dp/{asin}"
        
        try:
            logger.info(f"🔎 Checking {url}")
            resp = self.session.get(url, timeout=30)
            
            if resp.status_code != 200:
                logger.error(f"❌ HTTP {resp.status_code}")
                return None, None, None
                
            soup = BeautifulSoup(resp.text, 'lxml')
            
            title = soup.select_one('h1.a-size-large span, #productTitle, title')
            product_name = title.get_text().strip()[:80] if title else f"ASIN {asin}"
            
            # 🔥 PRIORITY 1: Nuclear Amazon Resale detection
            resale_price = self.find_amazon_resale_price_nuclear(soup)
            if resale_price:
                logger.info(f"🎯 AMAZON RESALE: ${resale_price:.2f} - {product_name[:50]}")
                return product_name, resale_price, 'resale'
            
            # Priority 2: Regular buybox
            buybox_price = self.find_any_price(soup)
            if buybox_price:
                logger.info(f"📦 Buybox: ${buybox_price:.2f} - {product_name[:50]}")
                return product_name, buybox_price, 'buybox'
                
            logger.warning(f"⚠️ No price found for {asin}")
            return None, None, None
            
        except Exception as e:
            logger.error(f"💥 Error {asin}: {e}")
            return None, None, None

    def check_price_change(self, asin, name, price, source):
        key = f"{asin}_{source}"
        old_price = self.price_history.get(key)
        
        if old_price != price:
            change = "DROPPED" if not old_price or price < old_price else "INCREASED"
            self.price_history[key] = price
            
            message = f"🔔 {name}\n💰 ${price:.2f} ({change})\n🔗 amazon.com/dp/{asin}"
            self.send_telegram(message)
            logger.info(f"🚨 {change}: ${price:.2f} {name[:50]} [{source}]")
        else:
            logger.info(f"✅ Stable: ${price:.2f} [{source}]")
            
        self.save_price_history()

    def send_telegram(self, message):
        if CONFIG['telegram_token'] == 'YOUR_BOT_TOKEN_HERE':
            return
        try:
            url = f"https://api.telegram.org/bot{CONFIG['telegram_token']}/sendMessage"
            requests.post(url, data={
                'chat_id': CONFIG['telegram_chat_id'],
                'text': message,
                'parse_mode': 'HTML'
            }, timeout=10)
        except:
            pass

    def run(self):
        logger.info(f"🎯 Nuclear tracker started - {len(CONFIG['asin_list'])} products")
        while True:
            for i, asin in enumerate(CONFIG['asin_list']):
                name, price, source = self.scrape_product(asin)
                if price:
                    self.check_price_change(asin, name, price, source)
                time.sleep(1 + i * 0.2)  # Rate limiting
                
            logger.info(f"😴 Sleeping {CONFIG['check_interval']/60} min...")
            time.sleep(CONFIG['check_interval'])

if __name__ == "__main__":
    tracker = AmazonTracker()
    tracker.run()
