#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
import logging.handlers
import multiprocessing as mp
import os
import ssl
import queue
import xmlrpc.client as xmlrpclib

import multiprocessing_logging

from scriptconfig import URL, DB, UID, PSW, WORKERS
from datetime import datetime

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
filename = os.path.basename(__file__)
logfile = os.path.splitext(filename)[0] + '.log'
fh = logging.FileHandler(logfile, mode='w')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
fh.setFormatter(formatter)
# add the handlers to logger
logger.addHandler(ch)
logger.addHandler(fh)
multiprocessing_logging.install_mp_handler(logger=logger)


# ==================================== SALE ORDER ====================================

def update_price(pid, data_pool, product_list):
    while True:
        try:
            socket = xmlrpclib.ServerProxy(URL, allow_none=True,context=ssl._create_unverified_context())
            data = data_pool.get_nowait()
        except queue.Empty:
            break
        try:
            sku = data.get('sku', '')
            id = data.get('id', '')
            product_dict = product_list.get(sku, '')
            if product_dict:
                if product_dict.get('not_available', False):
                    write_except = socket.execute(DB, UID, PSW, 'product.sku.reference', 'log_exception_error',
                                                  id,
                                                  "Temporarily unavailable")
                else:
                    create_vals = {'product_sku_ref_id': id,
                                   'item_name': product_dict.get('name', ''),
                                   'item_price': product_dict.get('price', 0),
                                   'update_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                   }
                    create_status = socket.execute(DB, UID, PSW, 'competitor.website.price', 'create', create_vals)

                    logger.info(f"writing info RD sku: {sku} Name:{product_dict.get('name', '')} Price: {product_dict.get('price', 0)}")

                    schedule_to_unlink = socket.execute(DB, UID, PSW, 'price.fetch.schedule', 'search',
                                                        [('product_sku_ref_id', '=', id)], 0, 1)
                    unlink_scheduled = schedule_to_unlink and socket.execute(DB, UID, PSW, 'price.fetch.schedule',
                                                                             'unlink', schedule_to_unlink)
            else:
                write_except = socket.execute(DB, UID, PSW, 'product.sku.reference', 'log_exception_error',
                                              id,
                                              "Couldn't fetch price due to unknown reason, please check if the product is added in the scrape list setup in restaurant depot website.")
        except Exception as e:
            logger.error('Exception --- error:{}'.format(e))
        finally:
            data_pool.task_done()

def restaurant_depot():
    manager = mp.Manager()
    data_pool = manager.JoinableQueue()
    sale_rep_ids = manager.dict()
    user_ids = manager.dict()
    socket = xmlrpclib.ServerProxy(URL, allow_none=True,context=ssl._create_unverified_context())
    product_list = {}
    with open('Allitems.csv', newline='') as f:
        csv_reader = csv.DictReader(f)
        old_upc = ''
        for vals in csv_reader:
            upc = vals['UPC']
            if vals.get('Unit/Case') == 'Total:':
                break
            if not upc:
                if vals['Est.Price'] == 'N/A':
                    product_list[upc] = {'not_available': True}
                    continue
                qty = float(vals['Qty'])
                price = float(vals['Est.Price'].strip('$'))
                unit_price = price/qty
                product_list[old_upc] = {'name': product_list[old_upc]['name'], 'price': unit_price, 'not_available': False}
                continue
            if vals['Est.Price'] == 'N/A':
                product_list[upc] = {'not_available': True}
                continue
            qty = float(vals['Qty'])
            price = float(vals['Est.Price'].strip('$'))
            unit_price = price/qty
            product_list[upc] = {'name': vals['Description'], 'price': unit_price, 'not_available': False}
            old_upc = upc

    queued_fetches = socket.execute(DB, UID, PSW, 'price.fetch.schedule', 'search_read', [],
                                    ['id', 'product_sku_ref_id'])
    queued_fetches_ids = [ele['id'] for ele in queued_fetches]
    queued_fetches = [ele['product_sku_ref_id'][0] for ele in queued_fetches]
    rdepot_skus = socket.execute(DB, UID, PSW, 'product.sku.reference', 'search_read',
                                 [('id', 'in', queued_fetches), ('competitor', '=', 'rdepot'),
                                  ('in_exception', '=', False)], ['id', 'competitor_sku'])

    rdepot_products = {sku['competitor_sku']: sku['id'] for sku in
                       rdepot_skus}

    for sku in rdepot_products:
        data_pool.put({'sku': sku, 'id': rdepot_products[sku]})

    workers = []
    for i in range(WORKERS):
        pid = "Worker-%d" % (i + 1)
        worker = mp.Process(name=pid, target=update_price,
                            args=(pid, data_pool, product_list))
        worker.start()
        workers.append(worker)

    data_pool.join()

if __name__ == "__main__":
    # SALE ORDER
    restaurant_depot()
