#!/usr/bin/env python3
import argparse
import logging
import multiprocessing as mp
import os
import random
import ssl
import sys
import time
import xmlrpc.client
from argparse import Namespace
from datetime import datetime
import csv

import multiprocessing_logging
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.common.by import By

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)
# create file handler which logs even debug messages
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(processName)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
# add the handlers to logger
logger.addHandler(ch)
multiprocessing_logging.install_mp_handler(logger=logger)

# Get configuration from environmental variables or command line
parser = argparse.ArgumentParser(description="Script to poll Odoo for scraping assignments")


def environ_or_required(key):
    """Helper to ensure args are set or an ENV variable is present"""
    if os.environ.get(key):
        return {'default': os.environ.get(key)}
    else:
        return {'required': True}


try:
    parser.add_argument('-a', '--attached', dest='headless', action='store_false', default=True,
                        help='Run in a browser window (default is headless)')

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
    parser.add_argument('-o', '--download-dir', dest="download_directory", default=os.environ.get("NSA_DOWNLOAD_DIR",
                                        os.environ.get("HOME") + "/Downloads"),
                                help="Download directory for browser. Default is $HOME/Downloads")
    parser.add_argument('-s', '--depot-sleep-time', dest="depot_sleep_time", type=int, default=75,
                                help="how long should we wait for Depot pages to load in seconds. Default 75.")

    env_depot_sleep_time: int = 0
    try:
        env_depot_sleep_time = int(os.environ.get("NSA_DEPOT_SLEEP_TIME", 0))
    except ValueError as e:
        logger.error("Environmental variable NSA_DEPOT_SLEEP_TIME is not an integer. Exiting.")
        logger.debug(e)
        sys.exit(1)

    args = parser.parse_args()  # type: Namespace
    url = args.url
    login = args.login
    pwd = args.pwd
    db = args.db
    poll_interval = args.poll_interval
    headless = args.headless
    download_directory = args.download_directory
    depot_sleep_time = env_depot_sleep_time or args.depot_sleep_time


except Exception as e:
    logger.error(e)
    sys.exit(1)

# Browser Configuration
options = Options()
options.headless = headless

# Socket Connection Configuration

socket = xmlrpc.client.ServerProxy(url + '/xmlrpc/object', context=ssl._create_unverified_context(), allow_none=True)


def odoo_writeback(create_vals, product_id, write_url=''):
    """
    The common method which is used to
    write values back into the odoo instance
    """
    socket = xmlrpc.client.ServerProxy(url + '/xmlrpc/object', context=ssl._create_unverified_context(),
                                       allow_none=True)
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
        logger.info("sleeping for %s seconds." % (nap_time))
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
            logger.error("Restaurant Depot login in failed. Retrying...", e)
            pass
    return driver

def restaurant_depot_scrape(driver):
    data = {}
    sleep_time = depot_sleep_time
    count = 1
    driver1 = driver
    while True:
        try:
            time.sleep(sleep_time)
            pop_button = driver.find_elements_by_xpath("//button[@class='action-secondary action-dismiss']")
            if len(pop_button) > 0:
                pop_button[0].click()
            my_list = driver.find_element_by_xpath("//button[@class='action action-auth-toggle user-shopping-list']")
            my_list.click()
            link = driver.find_element_by_xpath(
                "//div[@id='header-list-item-count']/div/ol[1]/li[1]/a")  # use li[1] for first list
            link.click()
            time.sleep(sleep_time)
            break


        except Exception as er:
            if count == 3:
                logger.error("***Restaurant Depot Page loading failed.***")
                return data
            logger.error("Restaurant Depot Page loading failed. Retrying...")
            sleep_time += 15
            count += 1
            driver = driver1

    count = 1
    driver1 = driver
    while True:
        try:
            print_button = driver.find_elements_by_xpath("//button[@id='print-export-list']")
            if len(print_button) > 0:
                print_button[0].click()
                time.sleep(depot_sleep_time)

            if os.path.isfile(download_directory + "/Allitems.csv"):
                os.remove(download_directory + "/Allitems.csv")

            export_button = driver.find_elements_by_xpath("//button[@id='export-to-excel']")

            if len(export_button) > 0:
                export_button[0].click()
                time.sleep(depot_sleep_time)
            break
        except Exception as er:
            if count == 3:
                logger.error("***Restaurant Depot export failed.***")
                return data
            logger.error("Restaurant Depot export failed. Retrying...")
            sleep_time += 15
            count += 1
            driver = driver1

    if os.path.isfile(download_directory + "/Allitems.csv"):
        with open(download_directory + "/Allitems.csv", newline='') as f:
            count = 1
            old_upc = ''
            for row in csv.reader(f):
                if count > 10:
                    if row[5] == 'Total:':
                        break

                    if row[7] == 'N/A':
                        upc = ''
                        if row[0]:
                            upc = row[0]
                            old_upc = row[0]
                        else:
                            upc = old_upc
                        data[upc] = {'not_available': True}
                        continue

                    qty = float(row[6])
                    price = float(row[7].strip('$').replace(',', ''))
                    unit_price = price
                    if qty > 0:
                        unit_price = price/qty

                    if not row[0]:
                        data[old_upc]['case_price'] = unit_price
                    else:
                        data[row[0]] = {'name': row[2], 'unit_price': unit_price, 'not_available': False}
                        old_upc = row[0]
                count+=1


    driver.quit()
    return data


def restaurant_depot(products, website_config):


    socket = xmlrpc.client.ServerProxy(url + '/xmlrpc/object', context=ssl._create_unverified_context(), allow_none=True)
    driver = webdriver.Firefox(options=options, service_log_path=os.path.devnull)

    # s = Service('/home/pauljose/projects/odoo-nsa/geckodriver')
    # driver = webdriver.Firefox(service=s)

    driver = restaurant_depot_login(driver, website_config)
    data = restaurant_depot_scrape(driver)
    # data = {elm.get('upc'): {e: elm[e] for e in list(elm.keys()) if e != 'upc'} for elm in data}

    if 'rdepot' in website_config:
        for sku in list(products.keys()):
            if sku in list(data.keys()):  # product found in the scraped list
                if data[sku].get('not_available', False):
                    write_except = socket.execute(db, login, pwd, 'product.sku.reference', 'log_exception_error',
                                                  products[sku][0],
                                                  "Temporarily unavailable")
                    continue
                item_name = data[sku].get('name')
                item_price = data[sku].get('unit_price')
                if data[sku].get('case_price'):
                    item_price = data[sku].get('case_price')
                logger.info(f"writing info RD sku: {sku} Name:{item_name} Price: {item_price}")
                create_vals = {'product_sku_ref_id': products[sku][0],
                               'item_name': item_name,
                               'item_price': item_price,
                               'update_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                               }

                res = odoo_writeback(create_vals, products[sku][0])

                schedule_to_unlink = socket.execute(db, login, pwd, 'price.fetch.schedule', 'search',
                                                    [('product_sku_ref_id', '=', products[sku][0])], 0, 1)
                unlink_scheduled = schedule_to_unlink and socket.execute(db, login, pwd, 'price.fetch.schedule',
                                                                         'unlink', schedule_to_unlink)

            else:  # product not found in scraped list log exception
                write_except = socket.execute(db, login, pwd, 'product.sku.reference', 'log_exception_error',
                                              products[sku][0],
                                              "Couldn't fetch price due to unknown reason, please check if the product is added in the scrape list setup in restaurant depot website.")
    return True


def webstaurant_store_fetch(driver, item, products, mode):
    try:
        unit_price = 0
        product_sku_id = products[item][0]

        if mode == 'search':
            search_box = driver.find_element_by_id('searchval')
            search_box.clear()
            search_box.send_keys(item)
            search_button = driver.find_element_by_xpath(
                "//button[@class='text-white hidden rounded-r border-0 box-border text-sm py-2.5 px-4-1/2 lt:flex lt:items-center cursor-pointer bg-blue-700 lt:hover:bg-blue-800 tracking-[.02em]']")
            search_button.click()

        if mode == 'url':
            driver.get(products[item][2])

        driver.implicitly_wait(random.randint(40, 45))
        item_url = driver.current_url

        soup_level2 = BeautifulSoup(driver.page_source, 'lxml')

        price_tr = soup_level2.findAll('div', {'class': 'pricing'})[0].findAll('tr')
        price = []
        name_tag = soup_level2.findAll('h1', {'id': 'page-header-description'})
        name = False
        if name_tag:
            name = name_tag[0].get_text()
        for tr in price_tr:
            if tr.find('td'):
                price.append(
                    float(tr.find('td').get_text().replace('\n', '').replace('\t', '').split('$')[-1].split('/')[0]))
        if price:
            unit_price = max(price)
        else:
            price_p = soup_level2.findAll('div', {'class': 'pricing'})[0].findAll('p')
            if price_p:
                unit_price = float(price_p[0].get_text().replace('$', '').split('/')[0])

        if unit_price:
            logger.info(f"writing info WS sku: {item}  Price: {unit_price}")
            create_vals = {'product_sku_ref_id': product_sku_id, 'item_name': name, 'item_price': unit_price,
                           'update_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            logger.info(f"create_vals: {create_vals}")
            res = odoo_writeback(create_vals, product_sku_id, write_url=item_url)

            return True
    except Exception as er:
        logger.error('----------------------Competitor SKU -------------------:', item)
        logger.error('Exception occurred', er)
    return False


def webstaurant_store(products, website_config):

    socket = xmlrpc.client.ServerProxy(url + '/xmlrpc/object', context=ssl._create_unverified_context(), allow_none=True)
    driver = webdriver.Firefox(options=options, service_log_path=os.path.devnull)

    # s = Service('/home/pauljose/projects/odoo-nsa/geckodriver')
    # driver = webdriver.Firefox(service=s)
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
                    logger.info("Could not find Webstaurant product in search. Redo the failed SKU with URL")
                    res = webstaurant_store_fetch(driver, item, products, 'url')
                random_sleep()

            except Exception as e:

                # if exception due to timeout, then recreate driver and repeat
                #                driver.close()
                driver.quit()
                logger.info("Closed Driver, Quit driver, Spawning new driver instance.................")
                driver = webdriver.Firefox(options, service_log_path=os.path.devnull)
                driver.get(login_url)
                driver.implicitly_wait(random.randint(40, 45))
                try:
                    res = webstaurant_store_fetch(driver, item, products, 'search')
                    if not res and products[item][2]:
                        logger.info("Could not find Webstaurant product in search. Redo the failed SKU with URL")
                        res = webstaurant_store_fetch(driver, item, products, 'url')
                    random_sleep()
                except Exception as er:
                    logger.error('Exception occurred for %s: %s' % (item, er))
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
        logger.error('Website Configuration required for Webstaurant Store')
    try:
        #        driver.close()
        driver.quit()
    except:
        logger.error('Cannot close driver. Exiting...')


def check_queued_fetches(login_config):

    socket = xmlrpc.client.ServerProxy(url + '/xmlrpc/object', context=ssl._create_unverified_context(), allow_none=True)
    logger.info('polling queue')
    queued_fetches = socket.execute(db, login, pwd, 'price.fetch.schedule', 'search_read', [('in_exception', '=', False)],
                                    ['id', 'product_sku_ref_id'])
    queued_fetches_ids = [ele['id'] for ele in queued_fetches]
    queued_fetches = [ele['product_sku_ref_id'][0] for ele in queued_fetches]
    rdepot_skus = socket.execute(db, login, pwd, 'product.sku.reference', 'search_read',
                                 [('id', 'in', queued_fetches), ('competitor', '=', 'rdepot'),
                                  ('in_exception', '=', False)], ['id', 'competitor_sku', 'website_link', 'qty_in_uom'])

    wdepot_skus = socket.execute(db, login, pwd, 'product.sku.reference', 'search_read',
                                 [('id', 'in', queued_fetches), ('competitor', '=', 'wdepot'),
                                  ('in_exception', '=', False)], ['id', 'competitor_sku', 'website_link', 'qty_in_uom'])
    rdepot_products = {}
    rdepot_products = {sku['competitor_sku']: (sku['id'], sku['qty_in_uom'], sku['website_link']) for sku in
                       rdepot_skus}
    wdepot_products = {sku['competitor_sku']: (sku['id'], sku['qty_in_uom'], sku['website_link']) for sku in
                       wdepot_skus}


    # Start Webstaurant Scraping if we have products in the queue
    logger.info('***Webstaurant Scraping***')
    webstaurant_worker = None
    if wdepot_products:
        webstaurant_worker = mp.Process(name="Webstaurant", target=webstaurant_store,
                                        args=(wdepot_products, login_config))
        webstaurant_worker.start()
    else:
        logger.info('No Webstaurant product in the queue')

    # logger.info('***Restaurant Depot Scraping***')

    restaurant_depot_worker = None
    if rdepot_products:
        restaurant_depot_worker = mp.Process(name="Restaurant_Depot", target=restaurant_depot,
                                             args=(rdepot_products, login_config))
        restaurant_depot_worker.start()
    else:
        logger.info('No Restaurant Depot product in the queue')

    # Wait for workers to finish their jobs
    if webstaurant_worker:
        webstaurant_worker.join()
    if restaurant_depot_worker:
        restaurant_depot_worker.join()
    return list(rdepot_products.keys()), list(wdepot_products.keys())


socket = xmlrpc.client.ServerProxy(url + '/xmlrpc/object', context=ssl._create_unverified_context(), allow_none=True)
while True:
    website_config = socket.execute(db, login, pwd, 'website.scraping.cofig', 'search_read', [],
                                    ['id', 'home_page_url', 'username', 'password', 'competitor'])
    login_config = {config['competitor']: (config['home_page_url'], config['username'], config['password']) for config
                    in website_config}
    if not login_config:
        logger.error('Website configuration required')
        sys.exit(1)
    rdepot_keys, wdepot_keys = check_queued_fetches(login_config)
    time.sleep(poll_interval)
