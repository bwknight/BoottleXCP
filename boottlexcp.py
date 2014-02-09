import sys
import os
import threading
import decimal
import time
import json
import logging
from bottle import route, run, template, Bottle, request, static_file, redirect, error, hook, response, abort
import boottleconf

sys.path.insert(0, boottleconf.COUNTERPARTYD_DIR)

from lib import (config, api, util, exceptions, bitcoin, blocks)
from lib import (send, order, btcpay, issuance, broadcast, bet, dividend, burn, cancel, callback)
from counterpartyd import set_options

D = decimal.Decimal

set_options()
db = util.connect_to_db()

app = Bottle()

def S(value):
    return int(D(value)*config.UNIT)

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o,  decimal.Decimal):
            return str(o)
        return super(DecimalEncoder, self).default(o)


@app.route('/static/<filename:path>')
def send_static(filename):
    return static_file(filename, root=os.path.join(os.path.dirname(__file__), 'static'))


@app.route('/')
def index():
    return static_file("boottlexcp.html", root=os.path.join(os.path.dirname(__file__), 'static'))


@app.route('/wallet')
def wallet():
    #total_table = PrettyTable(['Asset', 'Balance'])
    wallet = {'addresses': {}}
    totals = {}

    for group in bitcoin.rpc('listaddressgroupings', []):
        for bunch in group:
            address, btc_balance = bunch[:2]
            get_address = util.get_address(db, address=address)
            balances = get_address['balances']
            #table = PrettyTable(['Asset', 'Balance'])
            assets =  {}
            empty = True
            if btc_balance:
                #table.add_row(['BTC', btc_balance])  # BTC
                assets['BTC'] = btc_balance
                if 'BTC' in totals.keys(): totals['BTC'] += btc_balance
                else: totals['BTC'] = btc_balance
                empty = False
            for balance in balances:
                asset = balance['asset']
                balance = D(util.devise(db, balance['amount'], balance['asset'], 'output'))
                if balance:
                    if asset in totals.keys(): totals[asset] += balance
                    else: totals[asset] = balance
                    #table.add_row([asset, balance])
                    assets[asset] = balance
                    empty = False
            if not empty:
                wallet['addresses'][address] = assets

    wallet['totals'] = totals
    print(wallet)
    
    response.content_type = 'application/json'
    return json.dumps(wallet, cls=DecimalEncoder)


@app.post('/action')
def counterparty_action():
    unsigned = True

    try:
        action = request.forms.get('action')

        if action=='send':
            source = request.forms.get('source')
            destination = request.forms.get('destination')
            quantity = S(request.forms.get('quantity')) #TODO: fix. need float
            asset = request.forms.get('asset')        
            unsigned_tx_hex = send.create(db, source, destination, quantity, asset, unsigned=unsigned)
            result = {'success':True, 'message':str(unsigned_tx_hex)}       

        elif action=='order':
            source = request.forms.get('source')
            give_quantity = S(request.forms.get('give_quantity')) #TODO: fix. need float
            give_asset = request.forms.get('give_asset')
            get_quantity = S(request.forms.get('get_quantity')) #TODO: fix. need float
            get_asset = request.forms.get('get_asset')
            expiration = int(request.forms.get('expiration')) 
            fee_required = S(request.forms.get('fee_required'))             
            unsigned_tx_hex = order.create(db, source, give_asset,
                                           give_quantity, get_asset,
                                           get_quantity, expiration,
                                           fee_required, config.MIN_FEE / config.UNIT,
                                           unsigned=unsigned)
            result = {'success':True, 'message':str(unsigned_tx_hex)}       

        elif action=='btcpay':
            order_match_id = int(request.forms.get('order_match_id'))          
            unsigned_tx_hex = btcpay.create(db, order_match_id, unsigned=unsigned)
            result = {'success':True, 'message':str(unsigned_tx_hex)}          

        elif action=='cancel':
            offer_hash = request.forms.get('offer_hash')           
            unsigned_tx_hex = cancel.create(db, offer_hash, unsigned=unsigned)
            result = {'success':True, 'message':str(unsigned_tx_hex)}
           
        else:
            result = {'success':False, 'message':'Unknown action.'} 

        if result['success']==True and unsigned==False:
            tx_hash = bitcoin.transmit(unsigned_tx_hex, ask=False);
            result['message'] = "Transaction transmited: "+tx_hash

    except Exception as e:
        result = {'success':False, 'message':str(e)} 

    response.content_type = 'application/json'
    return json.dumps(result, cls=DecimalEncoder)


app.run(host=boottleconf.BOOTTLEXCP_HOST, port=boottleconf.BOOTTLEXCP_PORT, reloader=True)