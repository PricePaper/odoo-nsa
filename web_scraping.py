#!/usr/bin/env python2
import argparse
import logging
import os
import random
import ssl
import sys
import time
import xmlrpclib
from argparse import Namespace
from datetime import datetime

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.firefox.options import Options


from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import NoSuchElementException

# Log to stdout for containers
FORMAT = "%(asctime)-15s %(message)s"
logging.basicConfig(format=FORMAT, stream=sys.stdout, level=logging.INFO)

# Get configuration from environmental variables or command line
parser = argparse.ArgumentParser(description="Script to poll Odoo for scraping assignments")


def environ_or_required(key):
    """Helper to ensure args are set or an ENV variable is present"""
    if os.environ.get(key):
        return {'default': os.environ.get(key)}
    else:
        return {'required': True}


try:
    parser.add_argument('-u', '--url', dest='url', default=os.environ.get("NSA_XMLRPC_URI",
                                                                          'http://localhost:8069'),
                        help="XML-RPC host URL (default http://localhost:8069)")
    parser.add_argument('-l', '--login', dest='login', default=os.environ.get("NSA_USER",
                                                                              2),
                        help='user UID as an integer (default 1)', type=int)
    parser.add_argument('-p', '--password', dest='pwd', help='the password to login to Odoo (required)',
                        **environ_or_required("NSA_PASSWORD"))

    parser.add_argument('-d', '--database', dest='db', help='Odoo database (required)',
                        **environ_or_required("NSA_DB"))

    parser.add_argument('-i', '--interval', dest="poll_interval", default=os.environ.get("NSA_POLL_INTERVAL",
                                                                                         120),
                        type=int, help='interval to poll for work (default 120 sec)')

    args = parser.parse_args()  # type: Namespace
    url = args.url
    login = args.login
    pwd = args.pwd
    db = args.db
    poll_interval = args.poll_interval
except Exception as e:
    logging.error(e)
    sys.exit(1)

# Geckodriver Configuration
geckodriver_path = "/geckodriver"

# Browser Configuration
options = Options()
options.add_argument("--headless")  # declare the browser to run in headless mode

# Socket Connection Configuration
socket = xmlrpclib.ServerProxy(url + '/xmlrpc/object', context=ssl._create_unverified_context())


def odoo_writeback(create_vals, product_id, write_url=''):
    """
    The common method which is used to
    write values back into the odoo instance
    """
    if write_url:
        write_status = socket.execute(db, login, pwd, 'product.sku.reference', 'write', product_id,
                                      {'website_link': write_url})
    create_status = socket.execute(db, login, pwd, 'competitor.website.price', 'create', create_vals)


def random_sleep():
    """
    This method is used to introduce a random
    seconds of sleep time to the scraping process
    """
    ran_int = random.randint(0, 1)
    if ran_int == 1:
        nap_time = random.randint(4, 10)
        logging.info("sleeping for %s seconds." % (nap_time))
        time.sleep(nap_time)


def restaurant_depot_login(driver, website_config):
    login = False
    while not login:
         try:
            if 'rdepot' in website_config:
                login_url = website_config['rdepot'][0]
                username = website_config['rdepot'][1]
                password = website_config['rdepot'][2]

                driver.get(login_url)
                driver.implicitly_wait(40)
                uname = driver.find_element_by_id('email')
                uname.clear()
                uname.send_keys(username)

                pwd = driver.find_element_by_id('pass')
                pwd.clear()
                pwd.send_keys(password)

                submit_button = driver.find_element_by_id('send2')
                submit_button.click()

                driver.implicitly_wait(60)

                login = True
         except Exception as e:
             logging.error("restaurant depot logging in failed. Retrying...")
             pass
    return driver


def restaurant_depot_process_page(driver):
    scraped_data = []
    soup_string = BeautifulSoup(driver.page_source, 'lxml')

    for ele in soup_string.findAll('div', {'id': 'items-list'})[0].findAll('ol', {'class': 'products list items product-items'})[0].findAll('li', {'class': 'item product product-item'}):
        try:
            event_title = ele.find(class_='col-md-12 data-col').findAll('li')
            unit_price = ele.find('span', {'class': 'select-price'}) or False
            case_price = ''

            if unit_price:
                unit_price = unit_price.text.strip().strip('$')
            else:
                unit_price = ele.find('div', {'class': 'select-div-box'}) and ele.find('div', {'class': 'select-div-box'}).find('select', {'class': 'product-package-select'}).find('option', {'value': '1'}).text.strip().strip('Unit').strip().strip('$')
                case_price = ele.find('div', {'class': 'select-div-box'}) and ele.find('div', {'class': 'select-div-box'}).find('select', {'class': 'product-package-select'}).find('option', {'value': '2'}).text.strip().strip('Case').strip().strip('$')
            if unit_price:
                product = {}
                for index, li in enumerate(event_title):
                    if index == 0:
                        product['name'] = li.text.strip()
                    elif index == 1:
                        product['item'] = li.text.strip('Item:').strip()
                    elif index == 2:
                        product['upc'] = li.text.strip('UPC:').strip()
                    elif index == 3:
                        product['units_in_case'] = li.text.strip('Units per case:').strip() and float(li.text.strip('Units per case:').strip())
                        product['case_price'] = case_price and float(case_price)

                product['unit_price'] = unit_price and float(unit_price)

            scraped_data.append(product)
        except Exception er:
            logging.error('Exception occured', er)

    return scraped_data



def restaurant_depot_scrape(driver):
    data = []
    my_list = driver.find_element_by_xpath("//button[@class='action action-auth-toggle user-shopping-list']")
    my_list.click()
    link = driver.find_element_by_xpath("//div[@id='header-list-item-count']/div/ol[1]/li[1]/a")   # use li[1] for first list
    link.click()
    time.sleep(10)
    Select(driver.find_element_by_xpath("/html/body/div[1]/main/div[2]/div[1]/div[2]/div[5]/div/div/div[2]/div/div/select[@id='limiter']")).select_by_value('100')
    time.sleep(10)

    while True:
        try:
            data += restaurant_depot_process_page(driver)
        except Exception as er:
            logging.error('One page Skipped\n Error:', er)
        try:
            end_page = driver.find_element_by_xpath("/html/body/div[1]/main/div[2]/div[1]/div[2]/div[5]/div/div/div[3]/div/div[@class='item pages-item-next inactive']")
        except NoSuchElementException:
            end_page = False
        if end_page:
            break
        else:
            driver.find_element_by_xpath("/html/body/div[1]/main/div[2]/div[1]/div[2]/div[5]/div/div/div[3]/div/div[3]/a[@class='action  next']").click()
            time.sleep(20)
    driver.quit()
    return data


def restaurant_depot(products, website_config):
    driver = webdriver.Firefox(firefox_options=options, executable_path=geckodriver_path)
    driver = restaurant_depot_login(driver, website_config)
    data = restaurant_depot_scrape(driver)
    data = {elm.get('upc'): {e:elm[e] for e in elm.keys() if e != 'upc'} for elm in data}

    if 'rdepot' in website_config:
        for sku in products.keys():
            if sku in data.keys(): #product found in the scraped list

                logging.info("writing info sku:%s  Price:%s" % (sku, data[sku].get('unit_price')))
                create_vals = {'product_sku_ref_id': products[sku][0],
                               'item_name': data[sku].get('name'),
                               'item_price': data[sku].get('unit_price'),
                               'update_date': str(datetime.now()),
                               }
                res = odoo_writeback(create_vals, products[sku][0])

                schedule_to_unlink = socket.execute(db, login, pwd, 'price.fetch.schedule', 'search', [('product_sku_ref_id', '=', products[sku][0])], 0, 1)
                unlink_scheduled = schedule_to_unlink and socket.execute(db, login, pwd, 'price.fetch.schedule', 'unlink', schedule_to_unlink)

            else: #product not found in scraped list log exception
                write_except = socket.execute(db, login, pwd, 'product.sku.reference', 'log_exception_error', products[sku][0], "Couldn't fetch price due to unknown reason, please check if the product is added in the scrape list setup in restaurant depot website.")
    return True




def webstaurant_store_fetch(driver, item, products, mode):
    unit_price = 0
    product_sku_id = products[item][0]

    if mode == 'search':
        search_box = driver.find_element_by_id('searchval')
        search_box.clear()
        search_box.send_keys(item)
        search_button = driver.find_element_by_xpath("//button[@class='btn btn-info banner-search-btn']")
        search_button.click()

    if mode == 'url':
        driver.get(products[item][2])

    driver.implicitly_wait(random.randint(40, 45))
    item_url = driver.current_url

    soup_level2 = BeautifulSoup(driver.page_source, 'lxml')

    price_tr = soup_level2.findAll('div', {'class': 'pricing'})[0].findAll('tr')
    price = []
    name_tag = soup_level2.findAll('h1', {'itemprop': 'Name'})
    name = False
    if name_tag:
        name = name_tag[0].get_text()
    for tr in price_tr:
        if tr.find('td'):
            price.append(
                float(tr.find('td').get_text().replace('\n', '').replace('\t', '').replace('$', '').split('/')[0]))
    if price:
        unit_price = max(price)
    else:
        price_span = soup_level2.findAll('span', {'itemprop': 'price'})
        if price_span:
            unit_price = price_span[0].get_text()

    if unit_price:
        logging.info("writing info sku:%s  Price:%s" % (item, unit_price))
        create_vals = {'product_sku_ref_id': product_sku_id, 'item_name': name, 'item_price': unit_price,
                       'update_date': str(datetime.now())}
        res = odoo_writeback(create_vals, product_sku_id, write_url=item_url)
        return True
    return False


def webstaurant_store(products, website_config):
    driver = webdriver.Firefox(firefox_options=options, executable_path=geckodriver_path)
    item_url = ''
    if 'wdepot' in website_config:
        login_url = website_config['wdepot'][0]
        driver.get(login_url)
        driver.implicitly_wait(random.randint(40, 45))
        for item in products:
            res = False
            write_except = False
            try:
                res = webstaurant_store_fetch(driver, item, products, 'search')
                if not res and products[item][2]:
                    logging.info("could not find product in search. Redo the failed SKU with URL")
                    res = webstaurant_store_fetch(driver, item, products, 'url')
                random_sleep()

            except Exception as e:

                # if exception due to timeout, then recreate driver and repeat
                #                driver.close()
                driver.quit()
                logging.info("Closed Driver, Quit driver, Spawning new driver instance.................")
                driver = webdriver.Firefox(firefox_options=options, executable_path=geckodriver_path)
                driver.get(login_url)
                driver.implicitly_wait(random.randint(40, 45))
                try:
                    res = webstaurant_store_fetch(driver, item, products, 'search')
                    if not res and products[item][2]:
                        logging.info("could not find product in search. Redo the failed SKU with URL")
                        res = webstaurant_store_fetch(driver, item, products, 'url')
                    random_sleep()
                except Exception as er:
                    logging.error('Exception occured for %s: %s' % (item, er))
                    write_except = socket.execute(db, login, pwd, 'product.sku.reference', 'log_exception_error',
                                                  products[item][0], str(er))

            if res:
                schedule_to_unlink = socket.execute(db, login, pwd, 'price.fetch.schedule', 'search',
                                                    [('product_sku_ref_id', '=', products[item][0])], 0, 1)
                unlink_scheduled = schedule_to_unlink and socket.execute(db, login, pwd, 'price.fetch.schedule',
                                                                         'unlink', schedule_to_unlink)
            if not res and not write_except:
                write_except = socket.execute(db, login, pwd, 'product.sku.reference', 'log_exception_error',
                                              products[item][0],
                                              "Couldn't fetch price due to unknown reason, please check.")



    else:
        logging.error('Website Configuration required for Websturant Store')
    try:
        #        driver.close()
        driver.quit()
    except:
        logging.error('Cannot close driver. Exiting...')


def check_queued_fetches(login_config):
    logging.info('polling queue')
    queued_fetches = socket.execute(db, login, pwd, 'price.fetch.schedule', 'search_read', [],
                                    ['id', 'product_sku_ref_id'])
    queued_fetches_ids = [ele['id'] for ele in queued_fetches]
    queued_fetches = [ele['product_sku_ref_id'][0] for ele in queued_fetches]
    rdepot_skus = socket.execute(db, login, pwd, 'product.sku.reference', 'search_read',
                                 [('id', 'in', queued_fetches), ('competitor', '=', 'rdepot'),
                                  ('in_exception', '=', False)], ['id', 'competitor_sku', 'website_link', 'qty_in_uom'])
    wdepot_skus = socket.execute(db, login, pwd, 'product.sku.reference', 'search_read',
                                 [('id', 'in', queued_fetches), ('competitor', '=', 'wdepot'),
                                  ('in_exception', '=', False)], ['id', 'competitor_sku', 'website_link', 'qty_in_uom'])
    rdepot_products = {sku['competitor_sku']: (sku['id'], sku['qty_in_uom'], sku['website_link']) for sku in
                       rdepot_skus}
    wdepot_products = {sku['competitor_sku']: (sku['id'], sku['qty_in_uom'], sku['website_link']) for sku in
                       wdepot_skus}
    logging.info('***Webstaurant Scraping***')
    if wdepot_products:
        webstaurant_store(wdepot_products, login_config)
    else:
        logging.info('No webstaurant product in the queue')
    logging.info('***Restaurant Scraping***')
    if rdepot_products:
        restaurant_depot(rdepot_products, login_config)
    else:
        logging.info('No Restaurant depot product in the queue')
    return rdepot_products.keys(), wdepot_products.keys()


while True:
    website_config = socket.execute(db, login, pwd, 'website.scraping.cofig', 'search_read', [],
                                    ['id', 'home_page_url', 'username', 'password', 'competitor'])
    login_config = {config['competitor']: (config['home_page_url'], config['username'], config['password']) for config
                    in website_config}
    if not login_config:
        logging.error('Website configuration required')
        sys.exit(1)
    rdepot_keys, wdepot_keys = check_queued_fetches(login_config)
    time.sleep(poll_interval)
