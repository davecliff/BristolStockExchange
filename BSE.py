# -*- coding: utf-8 -*-
#
# BSE: The Bristol Stock Exchange
#
# Version 1.91: November 2024 fixed PT1 + PT2 parameter passing/unpacking
# Version 1.9: March 2024 added PT1+PT2, plus all the docstrings.
# Version 1.8; March 2023 added ZIPSH
# Version 1.7; September 2022 added PRDE
# Version 1.6; September 2021 added PRSH
# Version 1.5; 02 Jan 2021 -- was meant to be the final version before switch to BSE2.x, but that didn't happen :-)
# Version 1.4; 26 Oct 2020 -- change to Python 3.x
# Version 1.3; July 21st, 2018 (Python 2.x)
# Version 1.2; November 17th, 2012 (Python 2.x)
#
# Copyright (c) 2012-2024, Dave Cliff
#
#
# ------------------------
#
# MIT Open-Source License:
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
# associated documentation files (the "Software"), to deal in the Software without restriction,
# including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all copies or substantial
# portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT
# LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#
# ------------------------
#
#
#
# BSE is a very simple simulation of automated execution traders
# operating on a very simple model of a limit order book (LOB) exchange's matching engine.
#
# major simplifications in this version:
#       (a) only one financial instrument being traded
#       (b) traders can only trade contracts of size 1
#       (c) each trader can have max of one order per single orderbook.
#       (d) traders can replace/overwrite earlier orders, and/or can cancel, with no fee/penalty imposed for doing so
#       (d) simply processes each order in sequence and republishes LOB to all traders
#           => no issues with exchange processing latency/delays or simultaneously issued orders.
#
# NB this code has been written to be readable/intelligible, not efficient!

import sys
import math
import random
import os
import time as chrono
import csv
from datetime import datetime

# a bunch of system constants (globals)
bse_sys_minprice = 1                    # minimum price in the system, in cents/pennies
bse_sys_maxprice = 500                  # maximum price in the system, in cents/pennies
# ticksize should be a param of an exchange (so different exchanges can have different ticksizes)
ticksize = 1  # minimum change in price, in cents/pennies


# an Order/quote has a trader id, a type (buy/sell) price, quantity, timestamp, and unique i.d.
class Order:
    """
    An Order: this is used both for client-orders from exogenous customers to the robot traders acting as sales traders,
    and for the trader-orders (aka quotes) sent by the robot traders to the BSE exchange.
    In both use-cases, an order has a trader-i.d., a type (buy/sell), price, quantity, timestamp, and unique quote-i.d.
    """

    def __init__(self, tid, otype, price, qty, time, qid):
        self.tid = tid  # trader i.d.
        self.otype = otype  # order type
        self.price = price  # price
        self.qty = qty  # quantity
        self.time = time  # timestamp
        self.qid = qid  # quote i.d. (unique to each quote)

    def __str__(self):
        return '[%s %s P=%03d Q=%s T=%5.2f QID:%d]' % \
               (self.tid, self.otype, self.price, self.qty, self.time, self.qid)


class OrderbookHalf:
    """
    OrderbookHalf is one side of the book: a list of bids or a list of asks, each sorted best-price-first,
    and with orders at the same price arranged by arrival time (oldest first) for time-priority processing.
    """

    def __init__(self, booktype, worstprice):
        """
        Create one side of the LOB
        :param booktype: specifies bid or ask side of the LOB.
        :param worstprice: the initial value of the worst price currently showing on the LOB.
        """
        # booktype: bids or asks?
        self.booktype = booktype
        # dictionary of orders received, indexed by Trader ID
        self.orders = {}
        # limit order book, dictionary indexed by price, with order info
        self.lob = {}
        # anonymized LOB, lists, with only price/qty info
        self.lob_anon = []
        # summary stats
        self.best_price = None
        self.best_tid = None
        self.worstprice = worstprice
        self.session_extreme = None    # most extreme price quoted in this session
        self.n_orders = 0  # how many orders?
        self.lob_depth = 0  # how many different prices on lob?

    def anonymize_lob(self):
        """
        anonymize a lob, strip out order details, format as a sorted list
        NB for asks, the sorting should be reversed
        :return: <nothing>
        """
        self.lob_anon = []
        for price in sorted(self.lob):
            qty = self.lob[price][0]
            self.lob_anon.append([price, qty])

    def build_lob(self):
        """
        Take a list of orders and build a limit-order-book (lob) from it
        NB the exchange needs to know arrival times and trader-id associated with each order
        also builds anonymized version (just price/quantity, sorted, as a list) for publishing to traders
        :return: lob as a dictionary (i.e., unsorted)
        """
        lob_verbose = False
        self.lob = {}
        for tid in self.orders:
            order = self.orders.get(tid)
            price = order.price
            if price in self.lob:
                # update existing entry
                qty = self.lob[price][0]
                orderlist = self.lob[price][1]
                orderlist.append([order.time, order.qty, order.tid, order.qid])
                self.lob[price] = [qty + order.qty, orderlist]
            else:
                # create a new dictionary entry
                self.lob[price] = [order.qty, [[order.time, order.qty, order.tid, order.qid]]]
        # create anonymized version
        self.anonymize_lob()
        # record best price and associated trader-id
        if len(self.lob) > 0:
            if self.booktype == 'Bid':
                self.best_price = self.lob_anon[-1][0]
            else:
                self.best_price = self.lob_anon[0][0]
            self.best_tid = self.lob[self.best_price][1][0][2]
        else:
            self.best_price = None
            self.best_tid = None

        if lob_verbose:
            print(self.lob)

    def book_add(self, order):
        """
        Add order to the dictionary holding the list of orders for one side of the LOB.
        Either overwrites old order from this trader
            or dynamically creates new entry in the dictionary
            so there is a max of one order per trader per list
        checks whether length or order list has changed, to distinguish addition/overwrite
        :param order: the order to be added to the book
        :return: character-string indicating whether order-book was added to or overwritten.
        """

        # if this is an ask, does the price set a new extreme-high record?
        if (self.booktype == 'Ask') and ((self.session_extreme is None) or (order.price > self.session_extreme)):
            self.session_extreme = int(order.price)

        # add the order to the book
        n_orders = self.n_orders
        self.orders[order.tid] = order
        self.n_orders = len(self.orders)
        self.build_lob()
        # print('book_add < %s %s' % (order, self.orders))
        if n_orders != self.n_orders:
            return 'Addition'
        else:
            return 'Overwrite'

    def book_del(self, order):
        """
        Delete order from the dictionary holding the orders for one half of the book.
        Assumes max of one order per trader per list.
        Checks that the Trader ID does actually exist in the dict before deletion.
        :param order: the order to be deleted.
        :return: <nothing>
        """
        if self.orders.get(order.tid) is not None:
            del (self.orders[order.tid])
            self.n_orders = len(self.orders)
            self.build_lob()
        # print('book_del %s', self.orders)

    def delete_best(self):
        """
        When the best bid/ask has been hit/lifted, delete it from the book.
        :return: TraderID of the deleted order is return-value, as counterparty to the trade.
        """

        best_price_orders = self.lob[self.best_price]
        best_price_qty = best_price_orders[0]
        best_price_counterparty = best_price_orders[1][0][2]
        if best_price_qty == 1:
            # here the order deletes the best price
            del (self.lob[self.best_price])
            del (self.orders[best_price_counterparty])
            self.n_orders = self.n_orders - 1
            if self.n_orders > 0:
                if self.booktype == 'Bid':
                    self.best_price = max(self.lob.keys())
                else:
                    self.best_price = min(self.lob.keys())
                self.lob_depth = len(self.lob.keys())
            else:
                self.best_price = self.worstprice
                self.lob_depth = 0
        else:
            # best_bid_qty>1 so the order decrements the quantity of the best bid
            # update the lob with the decremented order data
            self.lob[self.best_price] = [best_price_qty - 1, best_price_orders[1][1:]]

            # update the bid list: counterparty's bid has been deleted
            del (self.orders[best_price_counterparty])
            self.n_orders = self.n_orders - 1
        self.build_lob()
        return best_price_counterparty


class Orderbook(OrderbookHalf):
    """ Orderbook for a single tradeable asset: list of bids and list of asks """

    def __init__(self):
        """Construct a new orderbook"""

        self.bids = OrderbookHalf('Bid', bse_sys_minprice)
        self.asks = OrderbookHalf('Ask', bse_sys_maxprice)
        self.tape = []
        self.tape_length = 10000    # max events on in-memory tape (older events can be written to tape_dump file)
        self.quote_id = 0           # unique ID code for each quote accepted onto the book
        self.lob_string = ''        # character-string linearization of public lob items with nonzero quantities


class Exchange(Orderbook):
    """  Exchange's matching engine and limit order book"""

    def add_order(self, order, vrbs):
        """
        add an order to the exchange -- either match with a counterparty order on LOB, or add to LOB.
        :param order: the order to be added to the LOB
        :param vrbs: verbosity: if True, print a running commentary; if False, stay silent.
        :return: [order.qid, response] -- order.qid is the order's unique quote i.d., response is 'Overwrite'|'Addition'
        """
        # add a quote/order to the exchange and update all internal records; return unique i.d.
        order.qid = self.quote_id
        self.quote_id = order.qid + 1
        if vrbs:
            print('add_order QID=%d self.quote.id=%d' % (order.qid, self.quote_id))
        if order.otype == 'Bid':
            response = self.bids.book_add(order)
            best_price = self.bids.lob_anon[-1][0]
            self.bids.best_price = best_price
            self.bids.best_tid = self.bids.lob[best_price][1][0][2]
        else:
            response = self.asks.book_add(order)
            best_price = self.asks.lob_anon[0][0]
            self.asks.best_price = best_price
            self.asks.best_tid = self.asks.lob[best_price][1][0][2]
        return [order.qid, response]

    def del_order(self, time, order, tape_file, vrbs):
        """
        Delete an order from the exchange.
        :param time: the current time.
        :param order: the order to be deleted from the LOB.
        :param tape_file: if not None, write details of the cancellation to the tape file.
        :param vrbs: verbosity: if True, print a running commentary; if False, stay silent.
        :return: <nothing>
        """
        # delete a trader's quote/order from the exchange, update all internal records
        if vrbs:
            print('del_order QID=%d' % order.qid)
        if order.otype == 'Bid':
            self.bids.book_del(order)
            if self.bids.n_orders > 0:
                best_price = self.bids.lob_anon[-1][0]
                self.bids.best_price = best_price
                self.bids.best_tid = self.bids.lob[best_price][1][0][2]
            else:  # this side of book is empty
                self.bids.best_price = None
                self.bids.best_tid = None
            cancel_record = {'type': 'Cancel', 'time': time, 'order': order}
            if tape_file is not None:
                tape_file.write('CAN, %f, %d, Bid, %d\n' % (time, order.qid, order.price))
            self.tape.append(cancel_record)
            # right-truncate the tape so that it keeps only the most recent items
            self.tape = self.tape[-self.tape_length:]

        elif order.otype == 'Ask':
            self.asks.book_del(order)
            if self.asks.n_orders > 0:
                best_price = self.asks.lob_anon[0][0]
                self.asks.best_price = best_price
                self.asks.best_tid = self.asks.lob[best_price][1][0][2]
            else:  # this side of book is empty
                self.asks.best_price = None
                self.asks.best_tid = None
            
            cancel_record = {'type': 'Cancel', 'time': time, 'order': order}
            if tape_file is not None:
                tape_file.write('CAN, %f, %d, Ask, %d\n' % (time, order.qid, order.price))
            self.tape.append(cancel_record)
            # right-truncate the tape so that it keeps only the most recent items
            self.tape = self.tape[-self.tape_length:]
        else:
            # neither bid nor ask?
            sys.exit('bad order type in del_quote()')

    def process_order(self, time, order, tape_file, vrbs):
        """
        Process an order from a trader -- this is the BSE Matching Engine.
        :param time: the current time.
        :param order: the order to be processed.
        :param tape_file: if is not None then write details of transaction to tape_file
        :param vrbs: verbosity: if True, print a running commentary; if False, stay silent.
        :return: transaction_record if the order results in a transaction, otherwise None.
        """
        # receive an order and either add it to the relevant LOB (ie treat as limit order)
        # or if it crosses the best counterparty offer, execute it (treat as a market order)
        oprice = order.price
        counterparty = None
        price = None
        [qid, response] = self.add_order(order, vrbs)  # add it to the order lists -- overwriting any previous order
        order.qid = qid
        if vrbs:
            print('QUID: order.quid=%d' % order.qid)
            print('RESPONSE: %s' % response)
        best_ask = self.asks.best_price
        best_ask_tid = self.asks.best_tid
        best_bid = self.bids.best_price
        best_bid_tid = self.bids.best_tid
        if order.otype == 'Bid':
            if self.asks.n_orders > 0 and best_bid >= best_ask:
                # bid lifts the best ask
                if vrbs:
                    print("Bid $%s lifts best ask" % oprice)
                counterparty = best_ask_tid
                price = best_ask  # bid crossed ask, so use ask price
                if vrbs:
                    print('counterparty, price', counterparty, price)
                # delete the ask just crossed
                self.asks.delete_best()
                # delete the bid that was the latest order
                self.bids.delete_best()
        elif order.otype == 'Ask':
            if self.bids.n_orders > 0 and best_ask <= best_bid:
                # ask hits the best bid
                if vrbs:
                    print("Ask $%s hits best bid" % oprice)
                # remove the best bid
                counterparty = best_bid_tid
                price = best_bid  # ask crossed bid, so use bid price
                if vrbs:
                    print('counterparty, price', counterparty, price)
                # delete the bid just crossed, from the exchange's records
                self.bids.delete_best()
                # delete the ask that was the latest order, from the exchange's records
                self.asks.delete_best()
        else:
            # we should never get here
            sys.exit('process_order() given neither Bid nor Ask')
        # NB at this point we have deleted the order from the exchange's records
        # but the two traders concerned still have to be notified
        if vrbs:
            print('counterparty %s' % counterparty)
        if counterparty is not None:
            # process the trade
            if vrbs:
                print('>>>>>>>>>>>>>>>>>TRADE t=%010.3f $%d %s %s' % (time, price, counterparty, order.tid))
            transaction_record = {'type': 'Trade',
                                  'time': time,
                                  'price': price,
                                  'party1': counterparty,
                                  'party2': order.tid,
                                  'qty': order.qty
                                  }
            if tape_file is not None:
                tape_file.write('TRD, %f, %d\n' % (time, price))
            self.tape.append(transaction_record)
            # right-truncate the tape so that it keeps only the most recent items
            self.tape = self.tape[-self.tape_length:]

            return transaction_record
        else:
            return None

    def tape_dump(self, fname, fmode, tmode):
        """
        Currently tape_dump only writes a list of transactions (i.e., it ignores any cancellations)
        :param fname: filename to write to.
        :param fmode: file-open write/append mode.
        :param tmode: if set to 'wipe', wipes the tape clean after writing it to file.
        :return:
        """
        dumpfile = open(fname, fmode)
        dumpfile.write('Event Type, Time, Price\n')
        for tapeitem in self.tape:
            if tapeitem['type'] == 'Trade':
                dumpfile.write('Trd, %010.3f, %s\n' % (tapeitem['time'], tapeitem['price']))
        dumpfile.close()
        if tmode == 'wipe':
            self.tape = []

    def publish_lob(self, time, lob_file, vrbs):
        """
        Returns the public LOB data published by the exchange, 
        i.e. the version of the LOB that's accessible to the traders.
        :param time: the current time.
        :param lob_file: 
        :param vrbs: verbosity: if True, print a running commentary; if False, stay silent.
        :return: the public LOB data.
        """
        public_data = dict()
        public_data['time'] = time
        public_data['bids'] = {'best': self.bids.best_price,
                               'worst': self.bids.worstprice,
                               'n': self.bids.n_orders,
                               'lob': self.bids.lob_anon}
        public_data['asks'] = {'best': self.asks.best_price,
                               'worst': self.asks.worstprice,
                               'sess_hi': self.asks.session_extreme,
                               'n': self.asks.n_orders,
                               'lob': self.asks.lob_anon}
        public_data['QID'] = self.quote_id
        public_data['tape'] = self.tape

        if lob_file is not None:
            # build a linear character-string summary of only those prices on LOB with nonzero quantities
            lobstring = 'Bid:,'
            n_bids = len(self.bids.lob_anon)
            if n_bids > 0:
                lobstring += '%d,' % n_bids
                for lobitem in self.bids.lob_anon:
                    price_str = '%d,' % lobitem[0]
                    qty_str = '%d,' % lobitem[1]
                    lobstring = lobstring + price_str + qty_str
            else:
                lobstring += '0,'
            lobstring += 'Ask:,'
            n_asks = len(self.asks.lob_anon)
            if n_asks > 0:
                lobstring += '%d,' % n_asks
                for lobitem in self.asks.lob_anon:
                    price_str = '%d,' % lobitem[0]
                    qty_str = '%d,' % lobitem[1]
                    lobstring = lobstring + price_str + qty_str
            else:
                lobstring += '0,'
            # is this different to the last lob_string?
            if lobstring != self.lob_string:
                # write it
                lob_file.write('%.3f, %s\n' % (time, lobstring))
                # remember it
                self.lob_string = lobstring

        if vrbs:
            vstr = 'publish_lob: t=%f' % time
            vstr += ' BID_lob=%s' % public_data['bids']['lob']
            # vstr += 'best=%s; worst=%s; n=%s ' % (self.bids.best_price, self.bids.worstprice, self.bids.n_orders)
            vstr += ' ASK_lob=%s' % public_data['asks']['lob']
            # vstr += 'qid=%d' % self.quote_id
            print(vstr)

        return public_data


# #################--Traders below here--#############


# Trader superclass
# all Traders have a trader id, bank balance, blotter, and list of orders to execute
class Trader:
    """The parent class for all types of robot trader in BSE"""

    def __init__(self, ttype, tid, balance, params, time):
        """
        Initializes a generic trader with attributes common to all/most types of trader
        Some trader types (e.g. ZIP) then have additional specialised initialization steps
        :param ttype: the trader type
        :param tid: the trader I.D. (a non-negative integer)
        :param balance: how much money it has in the bank when it is created
        :param params: a set of parameter-values, for those trader-types that have parameters
        :param time: the time this trader was created
        """
        self.ttype = ttype          # what type / strategy this trader is
        self.tid = tid              # trader unique ID code
        self.balance = balance      # money in the bank
        self.params = params        # parameters/extras associated with this trader-type or individual trader.
        self.blotter = []           # record of trades executed
        self.blotter_length = 100   # maximum length of blotter
        self.orders = []            # customer orders currently being worked (fixed at len=1 in BSE1.x)
        self.n_quotes = 0           # number of quotes live on LOB
        self.birthtime = time       # used when calculating age of a trader/strategy
        self.profitpertime = 0      # profit per unit time
        self.profit_mintime = 60    # minimum duration in seconds for calculating profitpertime
        self.n_trades = 0           # how many trades has this trader done?
        self.lastquote = None       # record of what its last quote was

    def __str__(self):
        """ return a character-string that summarises a trader """
        return '[TID %s type %s balance %s blotter %s orders %s n_trades %s profitpertime %s]' \
               % (self.tid, self.ttype, self.balance, self.blotter, self.orders, self.n_trades, self.profitpertime)

    def add_order(self, order, vrbs):
        """
        What a trader calls when it receives a new customer order/assignment
        :param order: the customer order/assignment to be added
        :param vrbs: verbosity: if True, print a running commentary; if False, stay silent.
        :return response: string to indicate whether the trader needs to cancel its current order on the LOB
        """
        # in this version, trader has at most one order,
        # if allow more than one, this needs to be self.orders.append(order)
        if self.n_quotes > 0:
            # this trader has a live quote on the LOB, from a previous customer order
            # need response to signal cancellation/withdrawal of that quote
            response = 'LOB_Cancel'
        else:
            response = 'Proceed'
        self.orders = [order]
        if vrbs:
            print('add_order < response=%s' % response)
        return response

    def del_order(self, order):
        """What a trader calls when it wants to delete an existing customer order/assignment """
        if order is None:
            pass    # this line is purely to stop PyCharm from warning about order being an unused parameter
        # this is lazy: assumes each trader has only one customer order with quantity=1, so deleting sole order
        self.orders = []

    def profitpertime_update(self, time, birthtime, totalprofit):
        """
        Calculates the trader's profit per unit time, but only if it has been alive longer than profit_mintime
        This is to avoid situations where a trader is created and then immediately makes a profit and
        hence the profit per unit time is a sky-high value, because the time_alive divisor is close to zero.
        :param time: the current time.
        :param birthtime: the time when the trader was created.
        :param totalprofit: the trader's current total accumulated profit.
        :return: profit per second.
        """
        time_alive = (time - birthtime)
        if time_alive >= self.profit_mintime:
            profitpertime = totalprofit / time_alive
        else:
            # if it's not been alive long enough, divide it by mintime instead of actual time
            profitpertime = totalprofit / self.profit_mintime
        return profitpertime

    def bookkeep(self, time, trade, order, vrbs):
        """
        Update trader's individual records of transactions, profit/loss etc.
        :param trade: details of the transaction that took place.
        :param order: details of the customer order that led to the transaction.
        :param vrbs: verbosity: if True, print a running commentary; if False, stay silent.
        :param time: the current time.
        :return: <nothing>
        """
        outstr = ""
        for order in self.orders:
            outstr = outstr + str(order)

        self.blotter.append(trade)  # add trade record to trader's blotter
        self.blotter = self.blotter[-self.blotter_length:]  # right-truncate to keep to length

        # NB What follows is **LAZY** -- assumes all orders are quantity=1
        transactionprice = trade['price']
        if self.orders[0].otype == 'Bid':
            profit = self.orders[0].price - transactionprice
        else:
            profit = transactionprice - self.orders[0].price
        self.balance += profit
        self.n_trades += 1
        self.profitpertime = self.balance / (time - self.birthtime)

        if profit < 0:
            print(profit)
            print(trade)
            print(order)
            sys.exit('FAIL: negative profit')

        if vrbs:
            print('%s profit=%d balance=%d profit/time=%s' % (outstr, profit, self.balance, str(self.profitpertime)))
        self.del_order(order)  # delete the order

        # if the trader has multiple strategies (e.g. PRSH/PRDE/ZIPSH/ZIPDE) then there is more work to do...
        if hasattr(self, 'strats') and hasattr(self, 'active_strat'):
            if self.strats is not None:
                self.strats[self.active_strat]['profit'] += profit
                totalprofit = self.strats[self.active_strat]['profit']
                birthtime = self.strats[self.active_strat]['start_t']
                self.strats[self.active_strat]['pps'] = self.profitpertime_update(time, birthtime, totalprofit)

    def respond(self, time, lob, trade, vrbs):
        """
        Specify how a trader responds to events in the market.
        For Trader superclass, this is minimal action, but expect it to be overloaded by specific trading strategies.
        :param time:
        :param lob:
        :param trade:
        :param vrbs: verbosity: if True, print a running commentary; if False, stay silent.
        :return:
        """

        # any trader subclass with custom respond() must include this update of profitpertime
        self.profitpertime = self.profitpertime_update(time, self.birthtime, self.balance)
        return None


class TraderGiveaway(Trader):
    """
    Trader subclass Giveaway (GVWY): even dumber than a ZI-U: just give the deal away (but never make a loss)
    """

    def getorder(self, time, countdown, lob):
        """
        Create this trader's order to be sent to the exchange.
        :param time: the current time.
        :param countdown: how much time before market closes (not used by GVWY).
        :param lob: the current state of the LOB.
        :return: a new order from this trader.
        """
        # this test for negative countdown is purely to stop PyCharm warning about unused parameter value
        if countdown < 0:
            sys.exit('Negative countdown')

        if len(self.orders) < 1:
            order = None
        else:
            quoteprice = self.orders[0].price
            order = Order(self.tid,
                          self.orders[0].otype,
                          quoteprice,
                          self.orders[0].qty,
                          time, lob['QID'])
            self.lastquote = order
        return order


class TraderZIC(Trader):
    """
    Trader subclass ZI-C: after Gode & Sunder 1993
    """

    def getorder(self, time, countdown, lob):
        """
        Create this trader's order to be sent to the exchange.
        :param time: the current time.
        :param countdown: how much time before market closes (not used by ZIC).
        :param lob: the current state of the LOB.
        :return: a new order from this trader.
        """
        # this test for negative countdown is purely to stop PyCharm warning about unused parameter value
        if countdown < 0:
            sys.exit('Negative countdown')

        if len(self.orders) < 1:
            # no orders: return NULL
            order = None
        else:
            minprice = lob['bids']['worst']
            maxprice = lob['asks']['worst']
            qid = lob['QID']
            limit = self.orders[0].price
            otype = self.orders[0].otype
            if otype == 'Bid':
                quoteprice = random.randint(int(minprice), int(limit))
            else:
                quoteprice = random.randint(int(limit), int(maxprice))
                # NB should check it == 'Ask' and barf if not
            order = Order(self.tid, otype, quoteprice, self.orders[0].qty, time, qid)
            self.lastquote = order
        return order


class TraderShaver(Trader):
    """
    Trader subclass Shaver: shaves a penny off the best price;
    but if there is no best price, creates "stub quote" at system max/min
    """

    def getorder(self, time, countdown, lob):
        """
        Create this trader's order to be sent to the exchange.
        :param time: the current time.
        :param countdown: how much time before market close (not used by SHVR).
        :param lob: the current state of the LOB.
        :return: a new order from this trader.
        """
        # this test for negative countdown is purely to stop PyCharm warning about unused parameter value
        if countdown < 0:
            sys.exit('Negative countdown')

        if len(self.orders) < 1:
            order = None
        else:
            limitprice = self.orders[0].price
            otype = self.orders[0].otype
            if otype == 'Bid':
                if lob['bids']['n'] > 0:
                    quoteprice = lob['bids']['best'] + 1
                    if quoteprice > limitprice:
                        quoteprice = limitprice
                else:
                    quoteprice = lob['bids']['worst']
            else:
                if lob['asks']['n'] > 0:
                    quoteprice = lob['asks']['best'] - 1
                    if quoteprice < limitprice:
                        quoteprice = limitprice
                else:
                    quoteprice = lob['asks']['worst']
            order = Order(self.tid, otype, quoteprice, self.orders[0].qty, time, lob['QID'])
            self.lastquote = order
        return order


class TraderSniper(Trader):
    """
    Trader subclass Sniper (SNPR), inspired by Kaplan's Sniper, BSE version is based on Shaver,
    "lurks" until time remaining < threshold% of the trading session
    then gets increasing aggressive, increasing "shave thickness" as time runs out
    """

    def getorder(self, time, countdown, lob):
        """
        Create this trader's order to be sent to the exchange.
        :param time: the current time.
        :param countdown: how much time before market closes.
        :param lob: the current state of the LOB.
        :return: a new order from this trader.
        """
        lurk_threshold = 0.2
        shavegrowthrate = 3
        shave = int(1.0 / (0.01 + countdown / (shavegrowthrate * lurk_threshold)))
        if (len(self.orders) < 1) or (countdown > lurk_threshold):
            order = None
        else:
            limitprice = self.orders[0].price
            otype = self.orders[0].otype

            if otype == 'Bid':
                if lob['bids']['n'] > 0:
                    quoteprice = lob['bids']['best'] + shave
                    if quoteprice > limitprice:
                        quoteprice = limitprice
                else:
                    quoteprice = lob['bids']['worst']
            else:
                if lob['asks']['n'] > 0:
                    quoteprice = lob['asks']['best'] - shave
                    if quoteprice < limitprice:
                        quoteprice = limitprice
                else:
                    quoteprice = lob['asks']['worst']
            order = Order(self.tid, otype, quoteprice, self.orders[0].qty, time, lob['QID'])
            self.lastquote = order
        return order


class TraderPRZI(Trader):
    """
    Cliff's Parameterized-Response Zero-Intelligence (PRZI) trader -- pronounced "prezzie"
    but with added adaptive strategies, currently either...
       ++  a k-point Stochastic Hill-Climber (SHC) hence PRZI-SHC,
           PRZI-SHC pronounced "prezzy-shuck". Ticker symbol PRSH pronounced "purrsh";
    or
       ++ a simple differential evolution (DE) optimizer with pop_size=k, hence PRZE-DE or PRDE ('purdy")

    when optimizer == None then it implements plain-vanilla non-adaptive PRZI, with a fixed strategy-value.
    """

    @staticmethod
    def strat_csv_str(strat):
        """
        Return trader's strategy as a csv-format string
        (trivial in PRZI, but other traders with more complex strategies need this).
        :param strat: the strategy specification (for PRZI, a real number in [-1.0,+1.0]
        :return: the strategy as a scv-format string
        """
        csv_str = 's=,%+5.3f, ' % strat
        return csv_str

    def mutate_strat(self, s, mode):
        """
        How to mutate the PRZI strategy values when evolving / hill-climbing
        :param s: the strategy to be mutated
        :param mode:    'gauss'=> mutation is a draw from a zero-mean Gaussian;
                        'uniform_whole_range" => mutation is a draw from uniform distbn over [-1.0,+1.0].
                        'uniform_bounded_range" => mutation is a draw from a bounded unifrom distbn.
        :return: the mutated strategy value
        """
        s_min = self.strat_range_min
        s_max = self.strat_range_max
        if mode == 'gauss':
            sdev = 0.05
            newstrat = s
            while newstrat == s:
                newstrat = s + random.gauss(0.0, sdev)
                # truncate to keep within range
                newstrat = max(-1.0, min(1.0, newstrat))
        elif mode == 'uniform_whole_range':
            # draw uniformly from whole range
            newstrat = random.uniform(-1.0, +1.0)
        elif mode == 'uniform_bounded_range':
            # draw uniformly from bounded range
            newstrat = random.uniform(s_min, s_max)
        else:
            sys.exit('FAIL: bad mode in mutate_strat')
        return newstrat

    def strat_str(self):
        """
        Pretty-print a string summarising this trader's strategy/strategies
        :return: the string
        """
        string = '%s: %s active_strat=[%d]:\n' % (self.tid, self.ttype, self.active_strat)
        for s in range(0, self.k):
            strat = self.strats[s]
            stratstr = '[%d]: s=%+f, start=%f, $=%f, pps=%f\n' % \
                       (s, strat['stratval'], strat['start_t'], strat['profit'], strat['pps'])
            string = string + stratstr

        return string

    def __init__(self, ttype, tid, balance, params, time):
        """
        Construct a PRZI trader
        :param ttype: the ticker-symbol for the type of trader (its strategy)
        :param tid: the trader id
        :param balance: the trader's bank balance
        :param params: if params == "landscape-mapper" then it generates data for mapping the fitness landscape
        :param time: the current time.
        """

        vrbs = True

        Trader.__init__(self, ttype, tid, balance, params, time)

        # unpack the params
        # for all three of PRZI, PRSH, and PRDE params can include strat_min and strat_max
        # for PRSH and PRDE params should include values for optimizer and k
        # if no params specified then defaults to PRZI with strat values in [-1.0,+1.0]

        # default parameter values
        k = 1
        optimizer = None    # no optimizer => plain non-adaptive PRZI
        s_min = -1.0
        s_max = +1.0

        # did call provide different params?
        if type(params) is dict:
            if 'k' in params:
                k = params['k']
            if 'optimizer' in params:
                optimizer = params['optimizer']
            s_min = params['strat_min']
            s_max = params['strat_max']

        self.optmzr = optimizer     # this determines whether it's PRZI, PRSH, or PRDE
        self.k = k                  # number of sampling points (cf number of arms on a multi-armed-bandit, or pop-size)
        self.theta0 = 100           # threshold-function limit value
        self.m = 4                  # tangent-function multiplier
        self.strat_wait_time = 7200     # how many secs do we give any one strat before switching?
        self.strat_range_min = s_min    # lower-bound on randomly-assigned strategy-value
        self.strat_range_max = s_max    # upper-bound on randomly-assigned strategy-value
        self.active_strat = 0       # which of the k strategies are we currently playing? -- start with 0
        self.prev_qid = None        # previous order i.d.
        self.strat_eval_time = self.k * self.strat_wait_time   # time to cycle through evaluating all k strategies
        self.last_strat_change_time = time  # what time did we last change strategies?
        self.profit_epsilon = 0.0 * random.random()    # min profit-per-sec difference between strategies that counts
        self.strats = []            # strategies awaiting initialization
        self.pmax = None            # this trader's estimate of the maximum price the market will bear
        self.pmax_c_i = math.sqrt(random.randint(1, 10))  # multiplier coefficient when estimating p_max
        self.mapper_outfile = None
        # differential evolution parameters all in one dictionary
        self.diffevol = {'de_state': 'active_s0',          # initial state: strategy 0 is active (being evaluated)
                         's0_index': self.active_strat,    # s0 starts out as active strat
                         'snew_index': self.k,             # (k+1)th item of strategy list is DE's new strategy
                         'snew_stratval': None,            # assigned later
                         'F': 0.8                          # differential weight -- usually between 0 and 2
                         }

        start_t = time
        profit = 0.0
        profit_per_second = 0
        lut_bid = None
        lut_ask = None

        for s in range(self.k + 1):
            # initialise each of the strategies in sequence:
            # for PRZI: only one strategy is needed
            # for PRSH, one random initial strategy, then k-1 mutants of that initial strategy
            # for PRDE, use draws from uniform distbn over whole range and a (k+1)th strategy is needed to hold s_new
            strategy = None
            if s == 0:
                strategy = random.uniform(self.strat_range_min, self.strat_range_max)
            else:
                if self.optmzr == 'PRSH':
                    # simple stochastic hill climber: cluster other strats around strat_0
                    strategy = self.mutate_strat(self.strats[0]['stratval'], 'gauss')     # mutant of strats[0]
                elif self.optmzr == 'PRDE':
                    # differential evolution: seed initial strategies across whole space
                    strategy = self.mutate_strat(self.strats[0]['stratval'], 'uniform_bounded_range')
                else:
                    # plain PRZI -- do nothing
                    pass
            # add to the list of strategies
            if s == self.active_strat:
                active_flag = True
            else:
                active_flag = False
            self.strats.append({'stratval': strategy, 'start_t': start_t, 'active': active_flag,
                                'profit': profit, 'pps': profit_per_second, 'lut_bid': lut_bid, 'lut_ask': lut_ask})
            if self.optmzr is None:
                # PRZI -- so we stop after one iteration
                break
            elif self.optmzr == 'PRSH' and s == self.k - 1:
                # PRSH -- doesn't need the (k+1)th strategy
                break

        if self.params == 'landscape-mapper':
            # replace seed+mutants set of strats with regularly-spaced strategy values over the whole range
            self.strats = []
            strategy_delta = 0.01
            strategy = -1.0
            k = 0
            self.strats = []

            while strategy <= +1.0:
                self.strats.append({'stratval': strategy, 'start_t': start_t, 'active': False,
                                    'profit': profit, 'pps': profit_per_second, 'lut_bid': lut_bid, 'lut_ask': lut_ask})
                k += 1
                strategy += strategy_delta
            self.mapper_outfile = open('landscape_map.csv', 'w')
            self.k = k
            self.strat_eval_time = self.k * self.strat_wait_time

        if vrbs:
            print("%s\n" % self.strat_str())

    def getorder(self, time, countdown, lob):
        """
        Create this trader's order to be sent to the exchange.
        :param time: the current time.
        :param countdown: how much time before market close (not used by GVWY).
        :param lob: the current state of the LOB.
        :return: a new order from this trader.
        """
        # this test for negative countdown is purely to stop PyCharm warning about unused parameter value
        if countdown < 0:
            sys.exit('Negative countdown')

        def shvr_price(order_type, lim, pub_lob):
            """
            Return value is what price a SHVR would quote in these circumstances
            :param order_type: is the order bid or ask?
            :param lim: limit price on the order.
            :param pub_lob: the current state of the published LOB.
            :return: The price a SHVR would quote given this LOB and limit-price.
            """

            if order_type == 'Bid':
                if pub_lob['bids']['n'] > 0:
                    shvr_p = pub_lob['bids']['best'] + ticksize   # BSE ticksize is global var
                    if shvr_p > lim:
                        shvr_p = lim
                else:
                    shvr_p = pub_lob['bids']['worst']
            else:
                if pub_lob['asks']['n'] > 0:
                    shvr_p = pub_lob['asks']['best'] - ticksize   # BSE ticksize is global var
                    if shvr_p < lim:
                        shvr_p = lim
                else:
                    shvr_p = pub_lob['asks']['worst']

            # print('shvr_p=%f; ' % shvr_p)
            return shvr_p

        def calc_cdf_lut(strategy, t0, m, dirn, pmin, pmax):
            """
            calculate cumulative distribution function (CDF) look-up table (LUT)
            :param strategy: strategy-value in [-1,+1]
            :param t0: constant used in the threshold function
            :param m: constant used in the threshold function
            :param dirn: direction: 'buy' or 'sell'
            :param pmin: lower bound on discrete-valued price-range
            :param pmax: upper bound on discrete-valued price-range
            :return: {'strat': strategy, 'dirn': dirn, 'pmin': pmin, 'pmax': pmax, 'cdf_lut': cdf}
            """

            # the threshold function used to clip
            def threshold(theta0, x):
                t = max(-1*theta0, min(theta0, x))
                return t

            epsilon = 0.000001  # used to catch DIV0 errors
            lut_vrbs = False

            if (strategy > 1.0) or (strategy < -1.0):
                # out of range
                sys.exit('PRSH FAIL: strategy=%f out of range\n' % strategy)

            if (dirn != 'buy') and (dirn != 'sell'):
                # out of range
                sys.exit('PRSH FAIL: bad dirn=%s\n' % dirn)

            if pmax < pmin:
                # screwed
                sys.exit('PRSH FAIL: pmax %f < pmin %f \n' % (pmax, pmin))

            if lut_vrbs:
                print('PRSH calc_cdf_lut: strategy=%f dirn=%d pmin=%d pmax=%d\n' % (strategy, dirn, pmin, pmax))

            p_range = float(pmax - pmin)
            if p_range < 1:
                # special case: the SHVR-style strategy has shaved all the way to the limit price
                # the lower and upper bounds on the interval are adjacent prices;
                # so cdf is simply the limit-price with probability 1

                if dirn == 'buy':
                    cdf = [{'price': pmax, 'cum_prob': 1.0}]
                else:   # must be a sell
                    cdf = [{'price': pmin, 'cum_prob': 1.0}]

                if lut_vrbs:
                    print('\n\ncdf:', cdf)

                return {'strat': strategy, 'dirn': dirn, 'pmin': pmin, 'pmax': pmax, 'cdf_lut': cdf}

            c = threshold(t0, m * math.tan(math.pi * (strategy + 0.5)))

            # catch div0 errors here
            if abs(c) < epsilon:
                if c > 0:
                    c = epsilon
                else:
                    c = -epsilon

            e2cm1 = math.exp(c) - 1

            # calculate the discrete calligraphic-P function over interval [pmin, pmax]
            # (i.e., this is Equation 8 in the PRZI Technical Note)
            calp_interval = []
            calp_sum = 0
            for p in range(pmin, pmax + 1):
                # normalize the price to proportion of its range
                p_r = (p - pmin) / p_range  # p_r in [0.0, 1.0]
                if strategy == 0.0:
                    # special case: this is just ZIC
                    cal_p = 1 / (p_range + 1)
                elif strategy > 0:
                    if dirn == 'buy':
                        cal_p = (math.exp(c * p_r) - 1.0) / e2cm1
                    else:   # dirn == 'sell'
                        cal_p = (math.exp(c * (1 - p_r)) - 1.0) / e2cm1
                else:   # self.strat < 0
                    if dirn == 'buy':
                        cal_p = 1.0 - ((math.exp(c * p_r) - 1.0) / e2cm1)
                    else:   # dirn == 'sell'
                        cal_p = 1.0 - ((math.exp(c * (1 - p_r)) - 1.0) / e2cm1)

                if cal_p < 0:
                    cal_p = 0   # just in case

                calp_interval.append({'price': p, "cal_p": cal_p})
                calp_sum += cal_p

            if calp_sum <= 0:
                print('calp_interval:', calp_interval)
                print('pmin=%f, pmax=%f, calp_sum=%f' % (pmin, pmax, calp_sum))

            cdf = []
            cum_prob = 0
            # now go thru interval summing and normalizing to give the CDF
            for p in range(pmin, pmax + 1):
                cal_p = calp_interval[p-pmin]['cal_p']
                prob = cal_p / calp_sum
                cum_prob += prob
                cdf.append({'price': p, 'cum_prob': cum_prob})

            if lut_vrbs:
                print('\n\ncdf:', cdf)

            return {'strat': strategy, 'dirn': dirn, 'pmin': pmin, 'pmax': pmax, 'cdf_lut': cdf}

        vrbs = False

        if vrbs:
            print('t=%.1f PRSH getorder: %s, %s' % (time, self.tid, self.strat_str()))

        if len(self.orders) < 1:
            # no orders: return NULL
            order = None
        else:
            # unpack the assignment-order
            limit = self.orders[0].price
            otype = self.orders[0].otype
            qid = self.orders[0].qid

            if self.prev_qid is None:
                self.prev_qid = qid

            if qid != self.prev_qid:
                # customer-order i.d. has changed, so we're working a new customer-order now
                # this is the time to switch arms
                # print("New order! (how does it feel?)")
                pass

            # get extreme limits on price interval
            # lowest price the market will bear
            minprice = int(lob['bids']['worst'])  # default assumption: worst bid price possible as defined by exchange

            # trader's individual estimate highest price the market will bear
            maxprice = self.pmax    # default assumption
            if self.pmax is None:
                maxprice = int(limit * self.pmax_c_i + 0.5)     # in the absence of any other info, guess
                self.pmax = maxprice
            elif lob['asks']['sess_hi'] is not None:
                if self.pmax < lob['asks']['sess_hi']:        # some other trader has quoted higher than I expected
                    maxprice = lob['asks']['sess_hi']         # so use that as my new estimate of highest
                    self.pmax = maxprice

            # use the cdf look-up table
            # cdf_lut is a list of little dictionaries
            # each dictionary has form: {'cum_prob':nnn, 'price':nnn}
            # generate u=U(0,1) uniform disrtibution
            # starting with the lowest nonzero cdf value at cdf_lut[0],
            # walk up the lut (i.e., examine higher cumulative probabilities),
            # until we're in the range of u; then return the relevant price

            strat = self.strats[self.active_strat]['stratval']

            # what price would a SHVR quote?
            p_shvr = shvr_price(otype, limit, lob)

            if otype == 'Bid':

                p_max = int(limit)
                if strat > 0.0:
                    p_min = minprice
                else:
                    # shade the lower bound on the interval
                    # away from minprice and toward shvr_price
                    p_min = int(0.5 + (-strat * p_shvr) + ((1.0 + strat) * minprice))

                lut_bid = self.strats[self.active_strat]['lut_bid']

                if (lut_bid is None) or \
                        (lut_bid['strat'] != strat) or (lut_bid['pmin'] != p_min) or (lut_bid['pmax'] != p_max):
                    # need to compute a new LUT
                    if vrbs:
                        print('New bid LUT')
                    self.strats[self.active_strat]['lut_bid'] = \
                        calc_cdf_lut(strat, self.theta0, self.m, 'buy', p_min, p_max)

                lut = self.strats[self.active_strat]['lut_bid']

            else:   # otype == 'Ask'

                p_min = int(limit)
                if strat > 0.0:
                    p_max = maxprice
                else:
                    # shade the upper bound on the interval
                    # away from maxprice and toward shvr_price
                    p_max = int(0.5 + (-strat * p_shvr) + ((1.0 + strat) * maxprice))
                    if p_max < p_min:
                        # this should never happen, but just in case it does...
                        p_max = p_min

                lut_ask = self.strats[self.active_strat]['lut_ask']

                if (lut_ask is None) or \
                        (lut_ask['strat'] != strat) or \
                        (lut_ask['pmin'] != p_min) or \
                        (lut_ask['pmax'] != p_max):
                    # need to compute a new LUT
                    if vrbs:
                        print('New ask LUT')
                    self.strats[self.active_strat]['lut_ask'] = \
                        calc_cdf_lut(strat, self.theta0, self.m, 'sell', p_min, p_max)

                lut = self.strats[self.active_strat]['lut_ask']

            vrbs = False
            if vrbs:
                print('PRZI strat=%f LUT=%s \n \n' % (strat, lut))
                # for debugging: print a table of lut: price and cum_prob, with the discrete derivative (gives PMF).
                last_cprob = 0.0
                for lut_entry in lut['cdf_lut']:
                    cprob = lut_entry['cum_prob']
                    print('%d, %f, %f' % (lut_entry['price'], cprob - last_cprob, cprob))
                    last_cprob = cprob
                print('\n')
                
                # print ('[LUT print suppressed]')
            
            # do inverse lookup on the LUT to find the price
            quoteprice = None
            u = random.random()
            for entry in lut['cdf_lut']:
                if u < entry['cum_prob']:
                    quoteprice = entry['price']
                    break

            order = Order(self.tid, otype, quoteprice, self.orders[0].qty, time, lob['QID'])

            self.lastquote = order

        return order

    def bookkeep(self, time, trade, order, vrbs):
        """
        Update trader's individual records of transactions, profit/loss etc.
        :param trade: details of the transaction that took place
        :param order: details of the customer order that led to the transaction
        :param vrbs: if True then print a running commentary of what's going on
        :param time: the current time
        :return: (nothing)
        """

        outstr = ""
        for order in self.orders:
            outstr = outstr + str(order)

        self.blotter.append(trade)  # add trade record to trader's blotter
        self.blotter = self.blotter[-self.blotter_length:]      # right-truncate to keep to length

        # NB What follows is **LAZY** -- assumes all orders are quantity=1
        transactionprice = trade['price']
        if self.orders[0].otype == 'Bid':
            profit = self.orders[0].price - transactionprice
        else:
            profit = transactionprice - self.orders[0].price
        self.balance += profit
        self.n_trades += 1
        self.profitpertime = self.balance / (time - self.birthtime)

        if profit < 0:
            print(profit)
            print(trade)
            print(order)
            sys.exit('PRSH FAIL: negative profit')

        if vrbs:
            print('%s profit=%d balance=%d profit/time=%d' % (outstr, profit, self.balance, self.profitpertime))
        self.del_order(order)  # delete the order

        self.strats[self.active_strat]['profit'] += profit
        time_alive = time - self.strats[self.active_strat]['start_t']
        if time_alive > 0:
            profit_per_second = self.strats[self.active_strat]['profit'] / time_alive
            self.strats[self.active_strat]['pps'] = profit_per_second
        else:
            # if it trades at the instant it is born then it would have infinite profit-per-second, which is insane
            # to keep things sensible when time_alive == 0 we say the profit per second is whatever the actual profit is
            self.strats[self.active_strat]['pps'] = profit

    def respond(self, time, lob, trade, vrbs):
        """
        Respond to the current state of the LOB.
        For strategy-optimizers PRSH and PRDE, this can involve switching stratregy, and/or generating new strategies.
        :param time: the current time.
        :param lob: the current state of the LOB.
        :param trade: details of most recent trade, if any.
        :param vrbs: if True then print messages explaining what is going on.
        :return:
        """
        # "PRSH" is a very basic form of stochastic hill-climber (SHC) that's v easy to understand and to code
        # it cycles through the k different strats until each has been operated for at least eval_time seconds
        # but a strat that does nothing will get swapped out if it's been running for no_deal_time without a deal
        # then the strats with the higher total accumulated profit is retained,
        # and mutated versions of it are copied into the other k-1 strats
        # then all counters are reset, and this is repeated indefinitely
        #
        # "PRDE" uses a basic form of Differential Evolution. This maintains a population of at least four strats
        # iterates indefinitely on:
        #       shuffle the set of strats;
        #       name the first four strats s0 to s3;
        #       create new_strat=s1+f*(s2-s3);
        #       evaluate fitness of s0 and new_strat;
        #       if (new_strat fitter than s0) then new_strat replaces s0.
        #
        # todo: add in other optimizer algorithms that are cleverer than these
        #  e.g. inspired by multi-arm-bandit algos like like epsilon-greedy, softmax, or upper confidence bound (UCB)

        def strat_activate(t, s_index):
            """
            Activate a specified strategy
            :param t: the current time
            :param s_index: the index of the strategy in the list of strategies
            :return: <nothing>
            """
            # print('t=%f Strat_activate, index=%d, active=%s' % (t, s_index, self.strats[s_index]['active'] ))
            self.strats[s_index]['start_t'] = t
            self.strats[s_index]['active'] = True
            self.strats[s_index]['profit'] = 0.0
            self.strats[s_index]['pps'] = 0.0

        vrbs = False

        # first update each active strategy's profit-per-second (pps) value -- this is the "fitness" of each strategy
        for s in self.strats:
            # debugging check: make profit be directly proportional to strategy, no noise
            # s['profit'] = 100 * abs(s['stratval'])
            # update pps
            active_flag = s['active']
            if active_flag:
                s['pps'] = self.profitpertime_update(time, s['start_t'], s['profit'])

        if self.optmzr == 'PRSH':

            if vrbs:
                # print('t=%f %s PRSH respond: shc_algo=%s eval_t=%f max_wait_t=%f' %
                #     (time, self.tid, shc_algo, self.strat_eval_time, self.strat_wait_time))
                pass

            # do we need to swap strategies?
            # this is based on time elapsed since last reset -- waiting for the current strategy to get a deal
            # -- otherwise a hopeless strategy can just sit there for ages doing nothing,
            # which would disadvantage the *other* strategies because they would never get a chance to score any profit.

            # NB this *cycles* through the available strats in sequence

            s = self.active_strat
            time_elapsed = time - self.last_strat_change_time
            if time_elapsed > self.strat_wait_time:
                # we have waited long enough: swap to another strategy
                self.strats[s]['active'] = False

                new_strat = s + 1
                if new_strat > self.k - 1:
                    new_strat = 0

                self.active_strat = new_strat
                self.strats[new_strat]['active'] = True
                self.last_strat_change_time = time

                if vrbs:
                    swt = self.strat_wait_time
                    print('t=%.3f (%.2fdays), %s PRSHrespond: strat[%d] elpsd=%.3f; wait_t=%.3f, pps=%f, new strat=%d' %
                          (time, time/86400, self.tid, s, time_elapsed, swt, self.strats[s]['pps'], new_strat))

            # code below here deals with creating a new set of k-1 mutants from the best of the k strats

            # assume that all strats have had long enough, and search for evidence to the contrary
            all_old_enough = True
            for s in self.strats:
                lifetime = time - s['start_t']
                if lifetime < self.strat_eval_time:
                    all_old_enough = False
                    break

            if all_old_enough:
                # all strategies have had long enough: which has made most profit?

                # sort them by profit
                strats_sorted = sorted(self.strats, key=lambda k: k['pps'], reverse=True)
                # strats_sorted = self.strats     # use this as a control: unsorts the strats, gives pure random walk.

                if vrbs:
                    print('PRSH %s: strat_eval_time=%f, all_old_enough=True' % (self.tid, self.strat_eval_time))
                    for s in strats_sorted:
                        print('s=%f, start_t=%f, lifetime=%f, $=%f, pps=%f' %
                              (s['stratval'], s['start_t'], time-s['start_t'], s['profit'], s['pps']))

                if self.params == 'landscape-mapper':
                    for s in self.strats:
                        self.mapper_outfile.write('time, %f, strat, %f, pps, %f\n' %
                                                  (time, s['stratval'], s['pps']))
                    self.mapper_outfile.flush()
                    sys.exit()

                else:
                    # if the difference between the top two strats is too close to call then flip a coin
                    # this is to prevent the same good strat being held constant simply by chance cos it is at index [0]
                    best_strat = 0
                    prof_diff = strats_sorted[0]['pps'] - strats_sorted[1]['pps']
                    if abs(prof_diff) < self.profit_epsilon:
                        # they're too close to call, so just flip a coin
                        best_strat = random.randint(0, 1)

                    if best_strat == 1:
                        # need to swap strats[0] and strats[1]
                        tmp_strat = strats_sorted[0]
                        strats_sorted[0] = strats_sorted[1]
                        strats_sorted[1] = tmp_strat

                    # the sorted list of strats replaces the existing list
                    self.strats = strats_sorted

                    # at this stage, strats_sorted[0] is our newly-chosen elite-strat, about to replicate

                    # now replicate and mutate the elite into all the other strats
                    for s in range(1, self.k):    # note range index starts at one not zero (elite is at [0])
                        self.strats[s]['stratval'] = self.mutate_strat(self.strats[0]['stratval'], 'gauss')
                        self.strats[s]['start_t'] = time
                        self.strats[s]['profit'] = 0.0
                        self.strats[s]['pps'] = 0.0
                    # and then update (wipe) records for the elite
                    self.strats[0]['start_t'] = time
                    self.strats[0]['profit'] = 0.0
                    self.strats[0]['pps'] = 0.0
                    self.active_strat = 0

                if vrbs:
                    print('%s: strat_eval_time=%f, MUTATED:' % (self.tid, self.strat_eval_time))
                    for s in self.strats:
                        print('s=%f start_t=%f, lifetime=%f, $=%f, pps=%f' %
                              (s['stratval'], s['start_t'], time-s['start_t'], s['profit'], s['pps']))

        elif self.optmzr == 'PRDE':
            # simple differential evolution

            # only initiate diff-evol once the active strat has been evaluated for long enough
            actv_lifetime = time - self.strats[self.active_strat]['start_t']
            if actv_lifetime >= self.strat_wait_time:

                if self.k < 4:
                    sys.exit('FAIL: k too small for diffevol')

                if self.diffevol['de_state'] == 'active_s0':
                    self.strats[self.active_strat]['active'] = False
                    # we've evaluated s0, so now we need to evaluate s_new
                    self.active_strat = self.diffevol['snew_index']
                    strat_activate(time, self.active_strat)

                    self.diffevol['de_state'] = 'active_snew'

                elif self.diffevol['de_state'] == 'active_snew':
                    # now we've evaluated s_0 and s_new, so we can do DE adaptive step
                    if vrbs:
                        print('PRDE trader %s' % self.tid)
                    i_0 = self.diffevol['s0_index']
                    i_new = self.diffevol['snew_index']
                    fit_0 = self.strats[i_0]['pps']
                    fit_new = self.strats[i_new]['pps']

                    if verbose:
                        print('DiffEvol: t=%.1f, i_0=%d, i0fit=%f, i_new=%d, i_new_fit=%f' %
                              (time, i_0, fit_0, i_new, fit_new))

                    if fit_new >= fit_0:
                        # new strat did better than old strat0, so overwrite new into strat0
                        self.strats[i_0]['stratval'] = self.strats[i_new]['stratval']

                    # do differential evolution

                    # pick four individual strategies at random, but they must be distinct
                    stratlist = list(range(0, self.k))    # create sequential list of strategy-numbers
                    random.shuffle(stratlist)             # shuffle the list

                    # s0 is next iteration's candidate for possible replacement
                    self.diffevol['s0_index'] = stratlist[0]

                    # s1, s2, s3 used in DE to create new strategy, potential replacement for s0
                    s1_index = stratlist[1]
                    s2_index = stratlist[2]
                    s3_index = stratlist[3]

                    # unpack the actual strategy values
                    s1_stratval = self.strats[s1_index]['stratval']
                    s2_stratval = self.strats[s2_index]['stratval']
                    s3_stratval = self.strats[s3_index]['stratval']

                    # this is the differential evolution "adaptive step": create a new individual
                    new_stratval = s1_stratval + self.diffevol['F'] * (s2_stratval - s3_stratval)

                    # clip to bounds
                    new_stratval = max(-1, min(+1, new_stratval))

                    # record it for future use (s0 will be evaluated first, then s_new)
                    self.strats[self.diffevol['snew_index']]['stratval'] = new_stratval

                    if verbose:
                        print('DiffEvol: t=%.1f, s0=%d, s1=%d, (s=%+f), s2=%d, (s=%+f), s3=%d, (s=%+f), sNew=%+f' %
                              (time, self.diffevol['s0_index'],
                               s1_index, s1_stratval, s2_index, s2_stratval, s3_index, s3_stratval, new_stratval))

                    # DC's intervention for fully converged populations
                    # is the stddev of the strategies in the population equal/close to zero?
                    strat_sum = 0.0
                    for s in range(self.k):
                        strat_sum += self.strats[s]['stratval']
                    strat_mean = strat_sum / self.k
                    sumsq = 0.0
                    for s in range(self.k):
                        diff = self.strats[s]['stratval'] - strat_mean
                        sumsq += (diff * diff)
                    strat_stdev = math.sqrt(sumsq / self.k)
                    if vrbs:
                        print('t=,%.1f, MeanStrat=, %+f, stdev=,%f' % (time, strat_mean, strat_stdev))
                    if strat_stdev < 0.0001:
                        # this population has converged
                        # mutate one strategy at random
                        randindex = random.randint(0, self.k - 1)
                        self.strats[randindex]['stratval'] = random.uniform(-1.0, +1.0)
                        if verbose:
                            print('Converged pop: set strategy %d to %+f' %
                                  (randindex, self.strats[randindex]['stratval']))

                    # set up next iteration: first evaluate s0
                    self.active_strat = self.diffevol['s0_index']
                    strat_activate(time, self.active_strat)

                    self.diffevol['de_state'] = 'active_s0'

                else:
                    sys.exit('FAIL: self.diffevol[\'de_state\'] not recognized')

        elif self.optmzr is None:
            # this is PRZI -- nonadaptive, no optimizer, nothing to change here.
            pass

        else:
            sys.exit('FAIL: bad value for self.optmzr')


class TraderZIP(Trader):
    """
    The Zero-Intelligence-Plus (ZIP) adaptive trading strategy of Cliff (1997).
    The code here implements the original ZIP, and also the strategy-optimizing variuants ZIPSH and ZIPDE.
    """

    # ZIP init key param-values are those used in Cliff's 1997 original HP Labs tech report
    # NB this implementation keeps separate margin values for buying & selling,
    #    so a single trader can both buy AND sell
    #    -- in the original, traders were either buyers OR sellers

    @staticmethod
    def strat_csv_str(strat):
        """
        Take a ZIP strategy vector and return it as a csv-format string.
        :param strat: the vector of values for the ZIP trader's strategy
        :return: the csv-format string.
        """
        if strat is None:
            csv_str = 'None, '
        else:
            csv_str = 'mBuy=,%+5.3f, mSel=,%+5.3f, b=,%5.3f, m=,%5.3f, ca=,%6.4f, cr=,%6.4f, ' % \
                      (strat['m_buy'], strat['m_sell'], strat['beta'], strat['momntm'], strat['ca'], strat['cr'])
        return csv_str

    @staticmethod
    def mutate_strat(s, mode):
        """
        How to mutate the strategy values when evolving / hill-climbing
        :param s: the strategy to be mutated.
        :param mode: specify Gaussian or some other form of distribution for the mutation delta (currently only Gauss).
        :return: the mutated strategy.
        """

        def gauss_mutate_clip(value, sdev, range_min, range_max):
            """
            Mutation of strategy-value by injection of zero-mean Gaussian noise, followed by clipping to keep in range.
            :param value: the value to be mutated.
            :param sdev: the standard deviation on the Gaussian noise.
            :param range_min: lower bound on the range.
            :param range_max: upper bound opn the range.
            :return: the mutated value.
            """
            mut_val = value
            while mut_val == value:
                mut_val = value + random.gauss(0.0, sdev)
                if mut_val > range_max:
                    mut_val = range_max
                elif mut_val < range_min:
                    mut_val = range_min
            return mut_val

        # mutate each element of a ZIP strategy independently
        # and clip each to remain within bounds
        if mode == 'gauss':
            big_sdev = 0.025
            small_sdev = 0.0025
            margin_buy = gauss_mutate_clip(s['m_buy'], big_sdev, -1.0, 0)
            margin_sell = gauss_mutate_clip(s['m_sell'], big_sdev, 0.0, 1.0)
            beta = gauss_mutate_clip(s['beta'], big_sdev, 0.0, 1.0)
            momntm = gauss_mutate_clip(s['momntm'], big_sdev, 0.0, 1.0)
            ca = gauss_mutate_clip(s['ca'], small_sdev, 0.0, 1.0)
            cr = gauss_mutate_clip(s['cr'], small_sdev, 0.0, 1.0)
            new_strat = {'m_buy': margin_buy, 'm_sell': margin_sell, 'beta': beta, 'momntm': momntm, 'ca': ca, 'cr': cr}
        else:
            sys.exit('FAIL: bad mode in mutate_strat')
        return new_strat

    def __init__(self, ttype, tid, balance, params, time):
        """
        Create a ZIP/ZIPSH/ZIPDE trader.
        :param ttype: the string identifying the trader-type (what strategy is this).
        :param tid: the trader i.d. string.
        :param balance: the starting bank balance for this trader.
        :param params: any additional parameters.
        :param time: the current time.
        """

        Trader.__init__(self, ttype, tid, balance, params, time)

        # this set of one-liner functions named init_*() are just to make the init params obvious for ease of editing
        # for ZIP, a strategy is specified as a 6-tuple: (margin_buy, margin_sell, beta, momntm, ca, cr)
        # the 'default' values mentioned in comments below come from Cliff 1997 -- good ranges for most situations

        def init_beta():
            """in Cliff 1997 the initial beta values are U(0.1, 0.5)"""
            return random.uniform(0.1, 0.5)

        def init_momntm():
            """in Cliff 1997 the initial momentum values are U(0.0, 0.1)"""
            return random.uniform(0.0, 0.1)

        def init_ca():
            # in Cliff 1997 c_a was a system constant, the same for all traders, set to 0.05
            # here we take the liberty of introducing some variation
            return random.uniform(0.01, 0.05)

        def init_cr():
            # in Cliff 1997 c_r was a system constant, the same for all traders, set to 0.05
            # here we take the liberty of introducing some variation
            return random.uniform(0.01, 0.05)

        def init_margin():
            # in Cliff 1997 the initial margin values are U(0.05, 0.35)
            return random.uniform(0.05, 0.35)

        def init_stratwaittime():
            # not in Cliff 1997: use whatever limits you think best.
            return 7200 + random.randint(0, 3600)

        # unpack the params
        # for ZIPSH and ZIPDE params should include values for optimizer and k
        # if no params specified then defaults to ZIP with strat values as in Cliff1997

        # default parameter values
        k = 1
        optimizer = None    # no optimizer => plain non-optimizing ZIP
        logging = False

        # did call provide different params?
        if type(params) is dict:
            if 'k' in params:
                k = params['k']
            if 'optimizer' in params:
                optimizer = params['optimizer']
            self.logfile = None
            if 'logfile' in params:
                logging = True
                logfilename = params['logfile'] + '_' + tid + '_log.csv'
                self.logfile = open(logfilename, 'w')

        # the following set of variables are needed for original ZIP *and* for its optimizing extensions e.g. ZIPSH
        self.logging = logging
        self.willing = 1
        self.able = 1
        self.job = None             # this gets switched to 'Bid' or 'Ask' depending on order-type
        self.active = False         # gets switched to True while actively working an order
        self.prev_change = 0        # this was called last_d in Cliff'97
        self.beta = init_beta()
        self.momntm = init_momntm()
        self.ca = init_ca()         # self.ca & self.cr were hard-coded in '97 but parameterised later
        self.cr = init_cr()
        self.margin = None          # this was called profit in Cliff'97
        self.margin_buy = -1.0 * init_margin()
        self.margin_sell = init_margin()
        self.price = None
        self.limit = None
        self.prev_best_bid_p = None     # best bid price on LOB on previous update
        self.prev_best_bid_q = None     # best bid quantity on LOB on previous update
        self.prev_best_ask_p = None     # best ask price on LOB on previous update
        self.prev_best_ask_q = None     # best ask quantity on LOB on previous update

        # the following set of variables are needed only by ZIP with added hyperparameter optimization (e.g. ZIPSH)
        self.k = k                  # how many strategies evaluated at any one time?
        self.optmzr = optimizer     # what form of strategy-optimizer we're using
        self.strats = None          # the list of strategies, each of which is a dictionary
        self.strat_wait_time = init_stratwaittime()     # how many secs do we give any one strat before switching?
        self.strat_eval_time = self.k * self.strat_wait_time  # time to cycle through evaluating all k strategies
        self.last_strat_change_time = time  # what time did we last change strategies?
        self.active_strat = 0       # which of the k strategies are we currently playing? -- start with 0
        self.profit_epsilon = 0.0 * random.random()     # min profit-per-sec difference between strategies that counts

        if self.optmzr is not None and k > 1:
            # we're doing some form of k-armed strategy-optimization with multiple strategies
            self.strats = []
            # strats[0] is whatever we've just assigned, and is the active strategy
            strategy = {'m_buy': self.margin_buy, 'm_sell': self.margin_sell, 'beta': self.beta,
                        'momntm': self.momntm, 'ca': self.ca, 'cr': self.cr}
            self.strats.append({'stratvec': strategy, 'start_t': time, 'active': True,
                                'profit': 0, 'pps': 0, 'evaluated': False})

            # rest of *initial* strategy set is generated from same distributions, but these are all inactive
            for s in range(1, k):
                strategy = {'m_buy': -1.0 * init_margin(), 'm_sell': init_margin(), 'beta': init_beta(),
                            'momntm': init_momntm(), 'ca': init_ca(), 'cr': init_cr()}
                self.strats.append({'stratvec': strategy, 'start_t': time, 'active': False,
                                    'profit': 0, 'pps': 0, 'evaluated': False})

        if self.logging:
            self.logfile.write('ZIP, Tid, %s, ttype, %s, optmzr, %s, strat_wait_time, %f, n_strats=%d:\n' %
                               (self.tid, self.ttype, self.optmzr, self.strat_wait_time, self.k))
            for s in self.strats:
                self.logfile.write(str(s)+'\n')

    def getorder(self, time, countdown, lob):
        """
        Create the next order for this trader
        :param time: the current time
        :param countdown: time remaining until market closes (not used in ZIP)
        :param lob: the current state of the LOB
        :return: this trader's next order.
        """
        # this test for negative countdown is purely to stop PyCharm warning about unused parameter value
        if countdown < 0:
            sys.exit('Negative countdown')

        if len(self.orders) < 1:
            self.active = False
            order = None
        else:
            self.active = True
            self.limit = self.orders[0].price
            self.job = self.orders[0].otype
            if self.job == 'Bid':
                # currently a buyer (working a bid order)
                self.margin = self.margin_buy
            else:
                # currently a seller (working a sell order)
                self.margin = self.margin_sell
            quoteprice = int(self.limit * (1 + self.margin))

            lastprice = -1  # dummy value for if there is no lastprice
            if self.lastquote is not None:
                lastprice = self.lastquote.price

            self.price = quoteprice
            order = Order(self.tid, self.job, quoteprice, self.orders[0].qty, time, lob['QID'])
            self.lastquote = order

            if self.logging and order.price != lastprice:
                self.logfile.write('%f, Order:, %s\n' % (time, str(order)))
        return order

    def respond(self, time, lob, trade, vrbs):
        """
        Update ZIP profit margin on basis of what happened in market.
        For ZIPSH and ZIPDE, also maybe switch strategy and/or generate new strategies to evaluate.
        :param time: the current time.
        :param lob: the current state of the LOB.
        :param trade: details of most recent trade, if any.
        :param vrbs: if True then print a running commentary of what is going on.
        :return: snapshot: if Ture, then the caller of respond() should print the next frame of system snapshot data.
        """
        # ZIP trader responds to market events, altering its margin
        # does this whether it currently has an order to work or not

        def target_up(price):
            """ Generate a higher target price by randomly perturbing given price"""
            ptrb_abs = self.ca * random.random()  # absolute shift
            ptrb_rel = price * (1.0 + (self.cr * random.random()))  # relative shift
            target = int(round(ptrb_rel + ptrb_abs, 0))
            # #                        print('TargetUp: %d %d\n' % (price,target))
            return target

        def target_down(price):
            """ Generate a lower target price by randomly perturbing given price"""
            ptrb_abs = self.ca * random.random()  # absolute shift
            ptrb_rel = price * (1.0 - (self.cr * random.random()))  # relative shift
            target = int(round(ptrb_rel - ptrb_abs, 0))
            # #                        print('TargetDn: %d %d\n' % (price,target))
            return target

        def willing_to_trade(price):
            """ Am I willing to trade at this price?"""
            willing = False
            if self.job == 'Bid' and self.active and self.price >= price:
                willing = True
            if self.job == 'Ask' and self.active and self.price <= price:
                willing = True
            return willing

        def profit_alter(price):
            """
            ZIP profit-margin update on basis of target price -- updates self.margin.
            :param price: the target price.
            :return: <nothing>
            """
            oldprice = self.price
            diff = price - oldprice
            change = ((1.0 - self.momntm) * (self.beta * diff)) + (self.momntm * self.prev_change)
            self.prev_change = change
            newmargin = ((self.price + change) / self.limit) - 1.0

            if self.job == 'Bid':
                if newmargin < 0.0:
                    self.margin_buy = newmargin
                    self.margin = newmargin
            else:
                if newmargin > 0.0:
                    self.margin_sell = newmargin
                    self.margin = newmargin

            # set the price from limit and profit-margin
            self.price = int(round(self.limit * (1.0 + self.margin), 0))

        def load_strat(stratvec, birthtime):
            """
            Copy the strategy vector into the ZIP trader's params and timestamp it.
            :param stratvec: the strategy vector.
            :param birthtime: the timestamp.
            :return: <nothing>
            """
            self.margin_buy = stratvec['m_buy']
            self.margin_sell = stratvec['m_sell']
            self.beta = stratvec['beta']
            self.momntm = stratvec['momntm']
            self.ca = stratvec['ca']
            self.cr = stratvec['cr']
            # bookkeeping
            self.n_trades = 0
            self.birthtime = birthtime
            self.balance = 0
            self.profitpertime = 0

        def strat_activate(t, s_index):
            """
            Activate a specified strategy-vector.
            :param t: the current time.
            :param s_index: the index of the strategy to be activated.
            :return: <nothing>
            """
            # print('t=%f Strat_activate, index=%d, active=%s' % (t, s_index, self.strats[s_index]['active'] ))
            self.strats[s_index]['start_t'] = t
            self.strats[s_index]['active'] = True
            self.strats[s_index]['profit'] = 0.0
            self.strats[s_index]['pps'] = 0.0
            self.strats[s_index]['evaluated'] = False

        # snapshot says whether the caller of respond() should print next frame of system snapshot data
        snapshot = False

        if self.optmzr == 'ZIPSH':

            # ZIP with simple-stochastic-hillclimber optimization of strategy (hyperparameter values)

            # NB this *cycles* through the available strats in sequence (i.e., it doesn't shuffle them)

            # first update the pps for each active strategy
            for s in self.strats:
                # update pps
                active_flag = s['active']
                if active_flag:
                    s['pps'] = self.profitpertime_update(time, s['start_t'], s['profit'])

            # have we evaluated all the strategies?
            # (could instead just compare active_strat to k, but checking them all in sequence is arguably clearer)
            # assume that all strats have been evaluated, and search for evidence to the contrary
            all_evaluated = True
            for s in self.strats:
                if s['evaluated'] is False:
                    all_evaluated = False
                    break

            if all_evaluated:
                # time to generate a new set/population of k candidate strategies
                # NB when the final strategy in the trader's set/popln is evaluated, the set is then sorted into
                # descending order of profitability, so when we get to here we know that strats[0] is elite

                if vrbs and self.tid == 'S00':
                    print('t=%.3f, ZIPSH %s: strat_eval_time=%.3f,' % (time, self.tid, self.strat_eval_time))
                    for s in self.strats:
                        print('%s, start_t=%f, $=%f, pps=%f' %
                              (self.strat_csv_str(s['stratvec']), s['start_t'], s['profit'], s['pps']))

                # if the difference between the top two strats is too close to call then flip a coin
                # this is to prevent the same good strat being held constant simply by chance cos it is at index [0]
                best_strat = 0
                prof_diff = self.strats[0]['pps'] - self.strats[1]['pps']
                if abs(prof_diff) < self.profit_epsilon:
                    # they're too close to call, so just flip a coin
                    best_strat = random.randint(0, 1)

                    if best_strat == 1:
                        # need to swap strats[0] and strats[1]
                        tmp_strat = self.strats[0]
                        self.strats[0] = self.strats[1]
                        self.strats[1] = tmp_strat

                # at this stage, strats[0] is our newly-chosen elite-strat, about to replicate & mutate

                # now replicate and mutate the elite into all the other strats
                for s in range(1, self.k):  # note range index starts at one not zero (elite is at [0])
                    self.strats[s]['stratvec'] = self.mutate_strat(self.strats[0]['stratvec'], 'gauss')
                    strat_activate(time, s)

                # and then update (wipe) records for the elite
                strat_activate(time, 0)

                # load the elite into the ZIP trader params
                load_strat(self.strats[0]['stratvec'], time)

                self.active_strat = 0

                if vrbs and self.tid == 'S00':
                    print('%s: strat_eval_time=%f, best_strat=%d, MUTATED:' %
                          (self.tid, self.strat_eval_time, best_strat))
                    for s in self.strats:
                        print('%s start_t=%.3f, lifetime=%.3f, $=%.3f, pps=%f' %
                              (self.strat_csv_str(s['stratvec']), s['start_t'], time - s['start_t'], s['profit'],
                               s['pps']))

            else:
                # we're still evaluating

                s = self.active_strat
                time_elapsed = time - self.strats[s]['start_t']
                if time_elapsed >= self.strat_wait_time:
                    # this strategy has had long enough: update records for this strategy, then swap to another strategy
                    self.strats[s]['active'] = False
                    self.strats[s]['profit'] = self.balance
                    self.strats[s]['pps'] = self.profitpertime
                    self.strats[s]['evaluated'] = True

                    new_strat = s + 1
                    if new_strat > self.k - 1:
                        # we've just evaluated the last of this trader's set of strategies
                        # sort the strategies into order of descending profitability
                        strats_sorted = sorted(self.strats, key=lambda k: k['pps'], reverse=True)

                        # use this as a control: unsorts the strats, gives pure random walk.
                        # strats_sorted = self.strats

                        # the sorted list of strats replaces the existing list
                        self.strats = strats_sorted

                        # signal that we want to record a system snapshot because this trader's eval loop finished
                        snapshot = True

                        # NB not updating self.active_strat here because next call to respond() generates new popln

                    else:
                        # copy the new strategy vector into the trader's params
                        load_strat(self.strats[new_strat]['stratvec'], time)
                        self.strats[new_strat]['start_t'] = time
                        self.active_strat = new_strat
                        self.strats[new_strat]['active'] = True
                        self.last_strat_change_time = time

                    if vrbs and self.tid == 'S00':
                        vstr = 't=%.3f (%.2fdays) %s ZIPSH respond:' % (time, time/86400, self.tid)
                        vstr += ' strat[%d] elapsed=%.3f; wait_t=%.3f, pps=%f' % \
                                (s, time_elapsed, self.strat_wait_time, self.strats[s]['pps'])
                        if new_strat > self.k - 1:
                            print(vstr)
                        else:
                            vstr += ' switching to strat[%d]: %s' %\
                                    (new_strat, self.strat_csv_str(self.strats[new_strat]['stratvec']))

        elif self.optmzr is None:
            # this is vanilla ZIP -- nonadaptive, no optimizer, nothing to change here.
            pass

        # what, if anything, has happened on the bid LOB?
        bid_improved = False
        bid_hit = False
        lob_best_bid_p = lob['bids']['best']
        lob_best_bid_q = None
        if lob_best_bid_p is not None:
            # non-empty bid LOB
            lob_best_bid_q = lob['bids']['lob'][-1][1]
            if (self.prev_best_bid_p is not None) and (self.prev_best_bid_p < lob_best_bid_p):
                # best bid has improved
                # NB doesn't check if the improvement was by self
                bid_improved = True
            elif trade is not None and ((self.prev_best_bid_p > lob_best_bid_p) or (
                    (self.prev_best_bid_p == lob_best_bid_p) and (self.prev_best_bid_q > lob_best_bid_q))):
                # previous best bid was hit
                bid_hit = True
        elif self.prev_best_bid_p is not None:
            # the bid LOB has been emptied: was it cancelled or hit?
            last_tape_item = lob['tape'][-1]
            if last_tape_item['type'] == 'Cancel':
                bid_hit = False
            else:
                bid_hit = True

        # what, if anything, has happened on the ask LOB?
        ask_improved = False
        ask_lifted = False
        lob_best_ask_p = lob['asks']['best']
        lob_best_ask_q = None
        if lob_best_ask_p is not None:
            # non-empty ask LOB
            lob_best_ask_q = lob['asks']['lob'][0][1]
            if (self.prev_best_ask_p is not None) and (self.prev_best_ask_p > lob_best_ask_p):
                # best ask has improved -- NB doesn't check if the improvement was by self
                ask_improved = True
            elif trade is not None and ((self.prev_best_ask_p < lob_best_ask_p) or (
                    (self.prev_best_ask_p == lob_best_ask_p) and (self.prev_best_ask_q > lob_best_ask_q))):
                # trade happened and best ask price has got worse, or stayed same but quantity reduced
                # -- assume previous best ask was lifted
                ask_lifted = True
        elif self.prev_best_ask_p is not None:
            # the ask LOB is empty now but was not previously: canceled or lifted?
            last_tape_item = lob['tape'][-1]
            if last_tape_item['type'] == 'Cancel':
                ask_lifted = False
            else:
                ask_lifted = True

        if vrbs and (bid_improved or bid_hit or ask_improved or ask_lifted):
            print('ZIP respond: B_improved', bid_improved, 'B_hit', bid_hit,
                  'A_improved', ask_improved, 'A_lifted', ask_lifted)

        deal = bid_hit or ask_lifted

        if self.job == 'Ask':
            # seller
            if deal:
                tradeprice = trade['price']
                if self.price <= tradeprice:
                    # could sell for more? raise margin
                    target_price = target_up(tradeprice)
                    profit_alter(target_price)
                elif ask_lifted and self.active and not willing_to_trade(tradeprice):
                    # wouldn't have got this deal, still working order, so reduce margin
                    target_price = target_down(tradeprice)
                    profit_alter(target_price)
            else:
                # no deal: aim for a target price higher than best bid
                if ask_improved and self.price > lob_best_ask_p:
                    if lob_best_bid_p is not None:
                        target_price = target_up(lob_best_bid_p)
                    else:
                        target_price = lob['asks']['worst']  # stub quote
                    profit_alter(target_price)

        if self.job == 'Bid':
            # buyer
            if deal:
                tradeprice = trade['price']
                if self.price >= tradeprice:
                    # could buy for less? raise margin (i.e. cut the price)
                    target_price = target_down(tradeprice)
                    profit_alter(target_price)
                elif bid_hit and self.active and not willing_to_trade(tradeprice):
                    # wouldn't have got this deal, still working order, so reduce margin
                    target_price = target_up(tradeprice)
                    profit_alter(target_price)
            else:
                # no deal: aim for target price lower than best ask
                if bid_improved and self.price < lob_best_bid_p:
                    if lob_best_ask_p is not None:
                        target_price = target_down(lob_best_ask_p)
                    else:
                        target_price = lob['bids']['worst']  # stub quote
                    profit_alter(target_price)

        # remember the best LOB data ready for next response
        self.prev_best_bid_p = lob_best_bid_p
        self.prev_best_bid_q = lob_best_bid_q
        self.prev_best_ask_p = lob_best_ask_p
        self.prev_best_ask_q = lob_best_ask_q

        # return value of respond() tells caller whether to print a new frame of system-snapshot data
        return snapshot


class TraderPT1(Trader):
    """
    A minimally simple propreitary trader that buys & sells to make profit

    PT1 long-only buy-and-hold strategy in pseudocode:

    1 wait until the market has been open for 5 minutes (to give prices a chance to settle)
    2 then repeat forever:
    2.1 if (I am not holding a unit)
    2.1.1  and (best ask price is "cheap" -- i.e., less than average of recent transaction prices)
    2.1.2  and (I have enough money in my bank to pay the asking price)
    2.2 then
    2.2.1   (buy the unit -- lift the ask)
    2.2.2   (remember the purchase-price I paid for it)
    2.3 else if (I am holding a unit)
    2.4 then
    2.4.1   (my asking-price is that unit’s purchase-price plus my profit margin)
    2.4.1   if (best bid price is more than my asking price)
    2.4.1   then
    2.4.1.1    (sell my unit -- hit the bid)
    2.4.1.2    (put the money in my bank)
    """

    def __init__(self, ttype, tid, balance, params, time):
        """
        Construct a PT1 trader
        :param ttype: the ticker-symbol for the type of trader (its strategy)
        :param tid: the trader id
        :param balance: the trader's bank balance
        :param params: a dictionary of optional parameter-values to override the defaults
        :param time: the current time.
        """
        
        init_verbose = True
        
        Trader.__init__(self, ttype, tid, balance, params, time)
        self.job = 'Buy'  # flag switches between 'Buy' & 'Sell'; shows what PT1 is currently trying to do
        self.last_purchase_price = None

        # Default parameter-values
        self.n_past_trades = 5      # how many recent trades used to compute average price (avg_p)?
        self.bid_percent = 0.9999   # what percentage of avg_p should best_ask be for this trader to bid
        self.ask_delta = 5          # how much (absolute value) to improve on purchase price

        # Did the caller provide different params?
        if type(params) is dict:
            if 'bid_percent' in params:
                self.bid_percent = params['bid_percent']
                if self.bid_percent > 1.0 or self.bid_percent < 0.01:
                    sys.exit('FAIL: self.bid_percent=%f not in range [0.01,1.0])' % self.bid_percent)
            if 'ask_delta' in params:
                self.ask_delta = params['ask_delta']
                if self.ask_delta < 0:
                    sys.exit('Fail: PT1 ask_delta can\'t be negative (it\'s an absolute value)')
            if 'n_past_trades' in params:
                self.n_past_trades = int(round(params['n_past_trades']))
                if self.n_past_trades < 1:
                    sys.exit('Fail: PT1 n_past trades must be 1 or more')
                    
        if init_verbose:
            print('PT1 init: n_past_trades=%d, bid_percent=%6.5f, ask_delta=%d\n'
                  % (self.n_past_trades, self.bid_percent, self.ask_delta))
            
    def getorder(self, time, countdown, lob):
        """
        return this trader's order when it is polled in the main market_session loop.
        :param time: the current time.
        :param countdown: the time remaining until market closes (not currently used).
        :param lob: the public lob.
        :return: trader's new order, or None.
        """
        # this test for negative countdown is purely to stop PyCharm warning about unused parameter value
        if countdown < 0:
            sys.exit('Negative countdown')

        if len(self.orders) < 1 or time < 5 * 60:
            order = None
        else:
            quoteprice = self.orders[0].price
            order = Order(self.tid,
                          self.orders[0].otype,
                          quoteprice,
                          self.orders[0].qty,
                          time, lob['QID'])
            self.lastquote = order
        return order

    def respond(self, time, lob, trade, vrbs):
        """
        Respond to the current state of the public lob.
        Buys if best bid is less than simple moving average of recent transcaction prices.
        Sells as soon as it can make an acceptable profit.
        :param time: the current time
        :param lob: the current public lob
        :param trade:
        :param vrbs: verbosity -- if True then print running commentary, else stay silent
        :return: <nothing>
        """

        vstr = 't=%f PT1 respond: ' % time

        # what is average price of most recent n trades?
        # work backwards from end of tape (most recent trade)
        tape_position = -1
        n_prices = 0
        sum_prices = 0
        avg_price_ok = False
        avg_price = -1
        while n_prices < self.n_past_trades and abs(tape_position) < len(lob['tape']):
            if lob['tape'][tape_position]['type'] == 'Trade':
                price = lob['tape'][tape_position]['price']
                n_prices += 1
                sum_prices += price
            tape_position -= 1
        if n_prices == self.n_past_trades:
            # there's been enough trades to form an acceptable average
            avg_price = int(round(sum_prices / n_prices))
            avg_price_ok = True
        vstr += "avg_price_ok=%s, avg_price=%d " % (avg_price_ok, avg_price)

        # buying?
        if self.job == 'Buy' and avg_price_ok:
            vstr += 'Buying - '
            # see what's on the LOB
            if lob['asks']['n'] > 0:
                # there is at least one ask on the LOB
                best_ask = lob['asks']['best']
                if best_ask / avg_price < self.bid_percent:
                    # bestask is good value: send a spread-crossing bid to lift the ask
                    bidprice = best_ask + 1
                    if bidprice < self.balance:
                        # can afford to buy
                        # create the bid by issuing order to self, which will be processed in getorder()
                        order = Order(self.tid, 'Bid', bidprice, 1, time, lob['QID'])
                        self.orders = [order]
                        vstr += 'Best ask=%d, bidprice=%d, order=%s ' % (best_ask, bidprice, order)
                else:
                    vstr += 'bestask=%d >= avg_price=%d' % (best_ask, avg_price)
            else:
                vstr += 'No asks on LOB'
        # selling?
        elif self.job == 'Sell':
            vstr += 'Selling - '
            # see what's on the LOB
            if lob['bids']['n'] > 0:
                # there is at least one bid on the LOB
                best_bid = lob['bids']['best']
                # sell single unit at price of purchaseprice+askdelta
                askprice = self.last_purchase_price + self.ask_delta
                if askprice < best_bid:
                    # seems we have a buyer
                    # lift the ask by issuing order to self, which will processed in getorder()
                    order = Order(self.tid, 'Ask', askprice, 1, time, lob['QID'])
                    self.orders = [order]
                    vstr += 'Best bid=%d greater than askprice=%d order=%s ' % (best_bid, askprice, order)
                else:
                    vstr += 'Best bid=%d too low for askprice=%d ' % (best_bid, askprice)
            else:
                vstr += 'No bids on LOB'

        self.profitpertime = self.profitpertime_update(time, self.birthtime, self.balance)

        if vrbs:
            print(vstr)

    def bookkeep(self, time, trade, order, vrbs):
        """
        Update trader's records of its bank balance, current orders, and current job
        :param trade: the current time
        :param order: this trader's successful order
        :param vrbs: verbosity -- if True then print running commentary, else stay silent.
        :param time: the current time.
        :return: <nothing>
        """

        # output string outstr is printed if vrbs==True
        mins = int(time//60)
        secs = time - 60 * mins
        hrs = int(mins//60)
        mins = mins - 60 * hrs
        outstr = 't=%f (%dh%02dm%02ds) %s (%s) bookkeep: orders=' % (time, hrs, mins, secs, self.tid, self.ttype)
        for order in self.orders:
            outstr = outstr + str(order)

        self.blotter.append(trade)  # add trade record to trader's blotter

        # NB What follows is **LAZY** -- assumes all orders are quantity=1
        transactionprice = trade['price']
        if self.orders[0].otype == 'Bid':
            # Bid order succeeded, remember the price and adjust the balance
            self.balance -= transactionprice
            self.last_purchase_price = transactionprice
            self.job = 'Sell'  # now try to sell it for a profit
        elif self.orders[0].otype == 'Ask':
            # Sold! put the money in the bank
            self.balance += transactionprice
            self.last_purchase_price = 0
            self.job = 'Buy'  # now go back and buy another one
        else:
            sys.exit('FATAL: PT1 doesn\'t know .otype %s\n' % self.orders[0].otype)

        if vrbs:
            net_worth = self.balance + self.last_purchase_price
            print('%s Balance=%d NetWorth=%d' % (outstr, self.balance, net_worth))

        self.del_order(order)  # delete the order

    # end of PT1 definition


class TraderPT2(Trader):
    """
    A A minimally simple propreitary trader that buys & sells to make profit

    PT2 long-only buy-and-hold strategy in pseudocode:

    1 wait until the market has been open for 5 minutes (to give prices a chance to settle)
    2 then repeat forever:
    2.1 if (I am not holding a unit)
    2.1.1  and (best ask price is "cheap" -- i.e., less than average of recent transaction prices)
    2.1.2  and (I have enough money in my bank to pay the asking price)
    2.2 then
    2.2.1   (buy the unit -- lift the ask)
    2.2.2   (remember the purchase-price I paid for it)
    2.3 else if (I am holding a unit)
    2.4 then
    2.4.1   (my asking-price is that unit’s purchase-price plus my profit margin)
    2.4.1   if (best bid price is more than my asking price)
    2.4.1   then
    2.4.1.1    (sell my unit -- hit the bid)
    2.4.1.2    (put the money in my bank)
    """

    def __init__(self, ttype, tid, balance, params, time):
        """
        Construct a PT2 trader
        :param ttype: the ticker-symbol for the type of trader (its strategy)
        :param tid: the trader id
        :param balance: the trader's bank balance
        :param params: a dictionary of optional parameter-values to override the defaults
        :param time: the current time.
        """

        Trader.__init__(self, ttype, tid, balance, params, time)
        self.job = 'Buy'  # flag switches between 'Buy' & 'Sell'; shows what PT2 is currently trying to do
        self.last_purchase_price = None
        
        init_verbose = True

        # Default parameter-values
        self.n_past_trades = 5      # how many recent trades used to compute average price (avg_p)?
        self.bid_percent = 0.9999   # what percentage of avg_p should best_ask be for this trader to bid
        self.ask_delta = 5          # how much (absolute value) to improve on purchase price

        # Did the caller provide different params?
        if type(params) is dict:
            if 'bid_percent' in params:
                self.bid_percent = params['bid_percent']
                if self.bid_percent > 1.0 or self.bid_percent < 0.01:
                    sys.exit('FAIL: PT2 self.bid_percent=%f not in range [0.01,1.0])' % self.bid_percent)
            if 'ask_delta' in params:
                self.ask_delta = params['ask_delta']
                if self.ask_delta < 0:
                    sys.exit('Fail: PT2 ask_delta can\'t be negative (it\'s an absolute value)')
            if 'n_past_trades' in params:
                self.n_past_trades = int(round(params['n_past_trades']))
                if self.n_past_trades < 1:
                    sys.exit('Fail: PT2 n_past trades must be 1 or more')
                    
        if init_verbose:
            print('PT2 init: n_past_trades=%d, bid_percent=%6.5f, ask_delta=%d\n'
                  % (self.n_past_trades, self.bid_percent, self.ask_delta))

    def getorder(self, time, countdown, lob):
        """
        return this trader's order when it is polled in the main market_session loop.
        :param time: the current time.
        :param countdown: the time remaining until market closes (not currently used).
        :param lob: the public lob.
        :return: trader's new order, or None.
        """
        # this test for negative countdown is purely to stop PyCharm warning about unused parameter value
        if countdown < 0:
            sys.exit('Negative countdown')

        if len(self.orders) < 1 or time < 5 * 60:
            order = None
        else:
            quoteprice = self.orders[0].price
            order = Order(self.tid,
                          self.orders[0].otype,
                          quoteprice,
                          self.orders[0].qty,
                          time, lob['QID'])
            self.lastquote = order
        return order

    def respond(self, time, lob, trade, vrbs):
        """
        Respond to the current state of the public lob.
        Buys if best bid is less than simple moving average of recent transcaction prices.
        Sells as soon as it can make an acceptable profit.
        :param time: the current time
        :param lob: the current public lob
        :param trade:
        :param vrbs: if True then print running commentary, else stay silent
        :return: <nothing>
        """

        vstr = 't=%f PT2 respond: ' % time

        # what is average price of most recent n trades?
        # work backwards from end of tape (most recent trade)
        tape_position = -1
        n_prices = 0
        sum_prices = 0
        avg_price_ok = False
        avg_price = -1
        while n_prices < self.n_past_trades and abs(tape_position) < len(lob['tape']):
            if lob['tape'][tape_position]['type'] == 'Trade':
                price = lob['tape'][tape_position]['price']
                n_prices += 1
                sum_prices += price
            tape_position -= 1
        if n_prices == self.n_past_trades:
            # there's been enough trades to form an acceptable average
            avg_price = int(round(sum_prices / n_prices))
            avg_price_ok = True
        vstr += "avg_price_ok=%s, avg_price=%d " % (avg_price_ok, avg_price)

        # buying?
        if self.job == 'Buy' and avg_price_ok:
            vstr += 'Buying - '
            # see what's on the LOB
            if lob['asks']['n'] > 0:
                # there is at least one ask on the LOB
                best_ask = lob['asks']['best']
                if best_ask / avg_price < self.bid_percent:
                    # bestask is good value: send a spread-crossing bid to lift the ask
                    bidprice = best_ask + 1
                    if bidprice < self.balance:
                        # can afford to buy
                        # create the bid by issuing order to self, which will be processed in getorder()
                        order = Order(self.tid, 'Bid', bidprice, 1, time, lob['QID'])
                        self.orders = [order]
                        vstr += 'Best ask=%d, bidprice=%d, order=%s ' % (best_ask, bidprice, order)
                else:
                    vstr += 'bestask=%d >= avg_price=%d' % (best_ask, avg_price)
            else:
                vstr += 'No asks on LOB'
        # selling?
        elif self.job == 'Sell':
            vstr += 'Selling - '
            # see what's on the LOB
            if lob['bids']['n'] > 0:
                # there is at least one bid on the LOB
                best_bid = lob['bids']['best']
                # sell single unit at price of purchaseprice+askdelta
                askprice = self.last_purchase_price + self.ask_delta
                if askprice < best_bid:
                    # seems we have a buyer
                    # lift the ask by issuing order to self, which will processed in getorder()
                    order = Order(self.tid, 'Ask', askprice, 1, time, lob['QID'])
                    self.orders = [order]
                    vstr += 'Best bid=%d greater than askprice=%d order=%s ' % (best_bid, askprice, order)
                else:
                    vstr += 'Best bid=%d too low for askprice=%d ' % (best_bid, askprice)
            else:
                vstr += 'No bids on LOB'

        self.profitpertime = self.profitpertime_update(time, self.birthtime, self.balance)

        if vrbs:
            print(vstr)

    def bookkeep(self, time, trade, order, vrbs):
        """
        Update trader's records of its bank balance, current orders, and current job
        :param trade: the current time
        :param order: this trader's successful order
        :param vrbs: if True then print a running commentary, otherwise stay silent.
        :param time: the current time.
        :return: <nothing>
        """

        # output string outstr is printed if vrbs==True
        mins = int(time//60)
        secs = time - 60 * mins
        hrs = int(mins//60)
        mins = mins - 60 * hrs
        outstr = 't=%f (%dh%02dm%02ds) %s (%s) bookkeep: orders=' % (time, hrs, mins, secs, self.tid, self.ttype)
        for order in self.orders:
            outstr = outstr + str(order)

        self.blotter.append(trade)  # add trade record to trader's blotter

        # NB What follows is **LAZY** -- assumes all orders are quantity=1
        transactionprice = trade['price']
        if self.orders[0].otype == 'Bid':
            # Bid order succeeded, remember the price and adjust the balance
            self.balance -= transactionprice
            self.last_purchase_price = transactionprice
            self.job = 'Sell'  # now try to sell it for a profit
        elif self.orders[0].otype == 'Ask':
            # Sold! put the money in the bank
            self.balance += transactionprice
            self.last_purchase_price = 0
            self.job = 'Buy'  # now go back and buy another one
        else:
            sys.exit('FATAL: PT2 doesn\'t know .otype %s\n' % self.orders[0].otype)

        if vrbs:
            net_worth = self.balance + self.last_purchase_price
            print('%s Balance=%d NetWorth=%d' % (outstr, self.balance, net_worth))

        self.del_order(order)  # delete the order

    # end of PT2 definition

# ########################---trader-types have all been defined now--################


# #########################---Below lies the experiment/test-rig---##################


def trade_stats(expid, traders, dumpfile, time, lob):
    """
    Dump CSV statistics on exchange data and trader population to file for later analysis.
    This makes no assumptions about the number of types of traders, or the number of traders of any one type
    -- allows either/both to change between successive calls, but that does make it inefficient as it has to
    re-analyse the entire set of traders on each call.
    :param expid: the experiment-I.D. character-string.
    :param traders: the list of traders in the market.
    :param dumpfile: the file that will be written to.
    :param time: the current time.
    :param lob: the current state of the LOB.
    :return: <nothing>
    """

    # Analyse the set of traders, to see what types we have
    trader_types = {}
    for t in traders:
        ttype = traders[t].ttype
        if ttype in trader_types.keys():
            t_balance = trader_types[ttype]['balance_sum'] + traders[t].balance
            n = trader_types[ttype]['n'] + 1
        else:
            t_balance = traders[t].balance
            n = 1
        trader_types[ttype] = {'n': n, 'balance_sum': t_balance}

    # first two columns of output are the session_id and the time
    dumpfile.write('%s, %06d, ' % (expid, time))

    # second two columns of output are the LOB best bid and best offer (or 'None' if they're undefined)
    if lob['bids']['best'] is not None:
        dumpfile.write('%d, ' % (lob['bids']['best']))
    else:
        dumpfile.write('None, ')
    if lob['asks']['best'] is not None:
        dumpfile.write('%d, ' % (lob['asks']['best']))
    else:
        dumpfile.write('None, ')

    # total remaining number of columns printed depends on number of different trader-types at this timestep
    # for each trader type we print FOUR columns...
    # TraderTypeCode, TotalProfitForThisTraderType, NumberOfTradersOfThisType, AverageProfitPerTraderOfThisType
    for ttype in sorted(list(trader_types.keys())):
        n = trader_types[ttype]['n']
        s = trader_types[ttype]['balance_sum']
        dumpfile.write('%s, %d, %d, %f, ' % (ttype, s, n, s / float(n)))

    dumpfile.write('\n')


def populate_market(trdrs_spec, traders, shuffle, vrbs):
    """
    Create a bunch of traders from traders-specification.
    Optionally shuffles the pack of buyers and the pack of sellers.
    :param trdrs_spec: the specification of the population of traders.
    :param traders: the list into which the newly-created traders traders will be written, as a return parameter
    :param shuffle: whether to shuffle the ordering of buyers/sellers within the respective list.
    :param vrbs: verbosity Boolean: if True, print a running commentary; if False, stay silent.
    :return: tuple (n_buyers, n_sellers)
    """
    # trdrs_spec is a list of buyer-specs and a list of seller-specs
    # each spec is (<trader type>, <number of this type of trader>, optionally: <params for this type of trader>)

    def trader_type(robottype, name, parameters):
        """
        Create a newly instantiated trader of the designated type.
        :param robottype: the 'ticker-symbol' abbreviation indicating what type of trader to create.
        :param name: this trader's trader-I.D. character string.
        :param parameters: a list of parameter values for this trader-type.
        :return: a newly created trader of the designated type.
        """
        balance = 0.00
        proptrader_balance = 500  # marketmakers start with zero inventory and a balance of $500
        time0 = 0
        if robottype == 'GVWY':
            return TraderGiveaway('GVWY', name, balance, parameters, time0)
        elif robottype == 'ZIC':
            return TraderZIC('ZIC', name, balance, parameters, time0)
        elif robottype == 'SHVR':
            return TraderShaver('SHVR', name, balance, parameters, time0)
        elif robottype == 'SNPR':
            return TraderSniper('SNPR', name, balance, parameters, time0)
        elif robottype == 'ZIP':
            return TraderZIP('ZIP', name, balance, parameters, time0)
        elif robottype == 'ZIPSH':
            return TraderZIP('ZIPSH', name, balance, parameters, time0)
        elif robottype == 'PRZI':
            return TraderPRZI('PRZI', name, balance, parameters, time0)
        elif robottype == 'PRSH':
            return TraderPRZI('PRSH', name, balance, parameters, time0)
        elif robottype == 'PRDE':
            return TraderPRZI('PRDE', name, balance, parameters, time0)
        elif robottype == 'PT1':
            return TraderPT1('PT1', name, proptrader_balance, parameters, time0)
        elif robottype == 'PT2':
            return TraderPT2('PT2', name, proptrader_balance, parameters, time0)
        else:
            sys.exit('FATAL: don\'t know trader type %s\n' % robottype)

    def shuffle_traders(ttype_char, n, trader_list):
        """
        Shuffles the trader-I.D. character strings of the traders in trader_list
        :param ttype_char: the lead character on the trader-I.D. strings (B for buyer, S for seller, etc)
        :param n: how many traders of this type
        :param trader_list: the list of traders in which the shuffling happens
        :return: <nothing>
        """
        for swap in range(n):
            t1 = (n - 1) - swap
            t2 = random.randint(0, t1)
            t1name = '%c%02d' % (ttype_char, t1)
            t2name = '%c%02d' % (ttype_char, t2)
            trader_list[t1name].tid = t2name
            trader_list[t2name].tid = t1name
            temp = traders[t1name]
            trader_list[t1name] = trader_list[t2name]
            trader_list[t2name] = temp

    def unpack_params(trader_params, mapping):
        """
        Unpack the parameters for those trader-types that have them
        :param trader_params: the paramaters being passed to this trader.
        :param mapping: Boolean flag: if True, enable fitness-landscape-mapping; otherwise do nothing for mapping.
        :return: the dictionary of parameters for this trader.
        """

        parameters = None

        if ttype == 'ZIPSH' or ttype == 'ZIP':
            # parameters matter...
            if mapping:
                parameters = 'landscape-mapper'
            elif trader_params is not None:
                parameters = trader_params.copy()
                # trader-type determines type of optimizer used
                if ttype == 'ZIPSH':
                    parameters['optimizer'] = 'ZIPSH'
                else:   # ttype=ZIP
                    parameters['optimizer'] = None
        if ttype == 'PRSH' or ttype == 'PRDE' or ttype == 'PRZI':
            # parameters matter...
            if mapping:
                parameters = 'landscape-mapper'
            elif trader_params is not None:
                # params determines type of optimizer used
                if ttype == 'PRSH':
                    parameters = {'optimizer': 'PRSH', 'k': trader_params['k'],
                                  'strat_min': trader_params['s_min'], 'strat_max': trader_params['s_max']}
                elif ttype == 'PRDE':
                    parameters = {'optimizer': 'PRDE', 'k': trader_params['k'],
                                  'strat_min': trader_params['s_min'], 'strat_max': trader_params['s_max']}
                else:   # ttype=PRZI
                    parameters = {'optimizer': None, 'k': 1,
                                  'strat_min': trader_params['s_min'], 'strat_max': trader_params['s_max']}
            else:
                sys.exit('FAIL: PRZI/PRSH/PRDE trader needs one or more parameters to be specified')
                
        # for PT1/PT2 the parameters are optional...
        # ...and are unpacked in __init__, so here they're just passed straight on through
        if ttype == 'PT1':
            parameters = trader_params
        if ttype == 'PT2':
            parameters = trader_params

        return parameters

    landscape_mapping = False   # set to true when mapping fitness landscape (for PRSH etc).

    # the code that follows is a bit of a kludge, needs tidying up.
    n_buyers = 0
    for bs in trdrs_spec['buyers']:
        ttype = bs[0]
        for b in range(bs[1]):
            tname = 'B%02d' % n_buyers  # buyer i.d. string
            if len(bs) > 2:
                # third part of the buyer-spec is params for this trader-type
                params = unpack_params(bs[2], landscape_mapping)
            else:
                params = unpack_params(None, landscape_mapping)
            traders[tname] = trader_type(ttype, tname, params)
            n_buyers = n_buyers + 1

    if n_buyers < 1:
        sys.exit('FATAL: no buyers specified\n')

    if shuffle:
        shuffle_traders('B', n_buyers, traders)

    n_sellers = 0
    for ss in trdrs_spec['sellers']:
        ttype = ss[0]
        for s in range(ss[1]):
            tname = 'S%02d' % n_sellers  # buyer i.d. string
            if len(ss) > 2:
                # third part of the buyer-spec is params for this trader-type
                params = unpack_params(ss[2], landscape_mapping)
            else:
                params = unpack_params(None, landscape_mapping)
            traders[tname] = trader_type(ttype, tname, params)
            n_sellers = n_sellers + 1

    if n_sellers < 1:
        sys.exit('FATAL: no sellers specified\n')

    if shuffle:
        shuffle_traders('S', n_sellers, traders)

    n_proptraders = 0
    for pts in trdrs_spec['proptraders']:
        ttype = pts[0]
        for pt in range(pts[1]):
            tname = 'P%02d' % n_proptraders  # proptrader i.d. string
            if len(pts) > 2:
                # third part of the buyer-spec is params for this trader-type
                params = unpack_params(pts[2], landscape_mapping)
            else:
                params = unpack_params(None, landscape_mapping)
            traders[tname] = trader_type(ttype, tname, params)
            n_proptraders = n_proptraders + 1

    # NB markets with zero proptraders don't cause a fatal error

    if n_proptraders > 0 and shuffle:
        shuffle_traders('P', n_proptraders, traders)

    if vrbs:
        for t in range(n_buyers):
            tname = 'B%02d' % t
            print(traders[tname])
        for t in range(n_sellers):
            tname = 'S%02d' % t
            print(traders[tname])
        for t in range(n_proptraders):
            tname = 'P%02d' % t
            print(traders[tname])

    return {'n_buyers': n_buyers, 'n_sellers': n_sellers, 'n_proptraders': n_proptraders}


def customer_orders(time, traders, trader_stats, orders_sched, pending, vrbs):
    """
    Generate a list of new customer-orders to be issued to the traders in the immediate/near future,
    and a list of any existing customer-orders that need to be cancelled because they are overridden by new ones.
    :param time: the current time.
    :param traders: the population of traders.
    :param trader_stats: summary statistics about the population of traders.
    :param orders_sched: the supply/demand schedule from which the orders will be generated...
            os['timemode'] is either 'periodic', 'drip-fixed', 'drip-jitter', or 'drip-poisson';
            os['interval'] is number of seconds for a full cycle of replenishment;
            drip-poisson sequences will be normalised to ensure time of last replenishment <= interval.
            If a supply or demand schedule mode is "random" and more than one range is supplied in ranges[],
            then each time a price is generated one of the ranges is chosen equiprobably and the price is
            then generated uniform-randomly from that range.
            if len(range)==2, interpreted as min and max values on the schedule, specifying linear supply/demand curve.
            if len(range)==3, first two vals are min & max for linear sup/dem curves, and third value should be a
            callable function that generates a dynamic price offset; he offset value applies equally to the min & max,
            so gradient of linear sup/dem curves doesn't vary, but equilibrium price does.
            if len(range)==4, the third value is function that gives dynamic offset for schedule min, and 4th is a
            function giving dynamic offset for schedule max, so gradient of sup/dem linear curve can vary dynamically
            along with the varying equilibrium price.
    :param pending: the list of currently pending future orders if this is empty, generates a new one).
    :param vrbs: verbosity Boolean: if True, print a running commentary; if False, stay silent.
    :return: [new_pending, cancellations]:
            new_pending is list of new orders to be issued;
            cancellations is list of previously-issued orders now cancelled.
    """

    def sysmin_check(price):
        """ if price is less than system minimum price, issue a warning and clip the price to the minimum"""
        if price < bse_sys_minprice:
            print('WARNING: price < bse_sys_min -- clipped')
            price = bse_sys_minprice
        return price

    def sysmax_check(price):
        """ if price is greater than system maximum price, issue a warning and clip the price to the maximum"""
        if price > bse_sys_maxprice:
            print('WARNING: price > bse_sys_max -- clipped')
            price = bse_sys_maxprice
        return price

    def getorderprice(i, schedules, n, stepmode, orderissuetime):
        """
        Generate a price for an order, using the given supply/demand schedule, and specified step-mode.
        :param i: index of trader (position in list of traders).
        :param schedules: the supply/demand schedules.
        :param n: the number of traders that this schedule sup/dem is being applied to.
        :param stepmode: what type of steps to have between successive prices on the sup/dem schedule.
                stepmode=='fixed' => all steps are equal at one fixed size -- a "uniform-step" (see "jittered", below);
                stepmode=='jittered' => all steps are random, constrained to be within 2 uniform-steps of each other;
                stepmode=='random' => all steps are generated from a uniform distribution.
        :param orderissuetime: the time that this order will be issued at.
        :return: the price.
        """

        # does the first schedule range include optional dynamic offset function(s)?
        if len(schedules[0]) > 2:
            offsetfn = schedules[0][2]
            if callable(offsetfn[0]):
                # same offset for min and max
                offset_min = offsetfn[0](orderissuetime, *offsetfn[1])
                offset_max = offset_min
            else:
                sys.exit('FAIL: 3rd argument of sched in getorderprice() not callable')
            if len(schedules[0]) > 3:
                # if second offset function is specified, that applies only to the max value
                offsetfn = schedules[0][3]
                if callable(offsetfn):
                    # this function applies to max
                    offset_max = offsetfn(orderissuetime)
                else:
                    sys.exit('FAIL: 4th argument of sched in getorderprice() not callable')
        else:
            offset_min = 0.0
            offset_max = 0.0

        pmin = sysmin_check(offset_min + min(schedules[0][0], schedules[0][1]))
        pmax = sysmax_check(offset_max + max(schedules[0][0], schedules[0][1]))
        prange = pmax - pmin
        stepsize = prange / (n - 1)
        halfstep = round(stepsize / 2.0)

        if stepmode == 'fixed':
            order_price = pmin + int(i * stepsize)
        elif stepmode == 'jittered':
            order_price = pmin + int(i * stepsize) + random.randint(-halfstep, halfstep)
        elif stepmode == 'random':
            if len(schedules) > 1:
                # more than one schedule: choose one equiprobably
                s = random.randint(0, len(schedules) - 1)
                pmin = sysmin_check(min(schedules[s][0], schedules[s][1]))
                pmax = sysmax_check(max(schedules[s][0], schedules[s][1]))
            order_price = random.randint(int(pmin), int(pmax))
        else:
            sys.exit('FAIL: Unknown mode in schedule')
        order_price = sysmin_check(sysmax_check(order_price))
        return order_price

    def getissuetimes(n_traders, timemode, interval, shuffle, fittointerval):
        """
        Generate a list of issue/arrival times for a set of future customer-orders, over a specified time-interval.
        :param n_traders: how many traders need issue times (i.e., the number of customer orders to be generated)
        :param timemode: character-string specifying the temporal spacing of orders:
                timemode=='periodic'=> orders issued to all traders at the same instant in time, every time-interval;
                timemode=='drip-fixed'=> order interarrival time is exactly one timestep, for all orders;
                timemode=='drip-jitter'=> order interarrival time is (1+r)*timestep, r=U[0,timestep], for all orders;
                timemode=='drip-poisson'=> order interarrival time is a Poisson random process, for all orders.
        :param interval: the time-interval between successive order issuals/arrivals.
        :param shuffle: if True then shuffle the arrival times, randomising the sequence in which traders get orders.
        :param fittointerval: if True then final order arrives at exactly t+interval; else may be slightly later.
        :return: the list of issue times.
        """
        interval = float(interval)
        if n_traders < 1:
            sys.exit('FAIL: n_traders < 1 in getissuetime()')
        elif n_traders == 1:
            tstep = interval
        else:
            tstep = interval / (n_traders - 1)
        arrtime = 0
        issue_times = []
        for trdr in range(n_traders):
            if timemode == 'periodic':
                arrtime = interval
            elif timemode == 'drip-fixed':
                arrtime = trdr * tstep
            elif timemode == 'drip-jitter':
                arrtime = trdr * tstep + tstep * random.random()
            elif timemode == 'drip-poisson':
                # poisson requires a bit of extra work
                interarrivaltime = random.expovariate(n_traders / interval)
                arrtime += interarrivaltime
            else:
                sys.exit('FAIL: unknown time-mode in getissuetimes()')
            issue_times.append(arrtime)
            # at this point, arrtime is the last arrival time

        if fittointerval and ((arrtime > interval) or (arrtime < interval)):
            # generated sum of interarrival times longer than the interval
            # squish them back so that last arrival falls at t=interval
            for trdr in range(n_traders):
                issue_times[trdr] = interval * (issue_times[trdr] / arrtime)
        # optionally randomly shuffle the times
        if shuffle:
            for trdr in range(n_traders):
                i = (n_traders - 1) - trdr
                j = random.randint(0, i)
                tmp = issue_times[i]
                issue_times[i] = issue_times[j]
                issue_times[j] = tmp
        return issue_times

    def getschedmode(t_now, order_schedules):
        """
        return the step-mode for supply/demand schedule at the current time
        :param t_now: the current time
        :param order_schedules: dictionary/list of order schedules
        :return: schedrange = the price range for this schedule; mode= the stepmode for this schedule
        """
        got_one = False
        schedrange = None
        stepmode = None
        for schedule in order_schedules:
            if (schedule['from'] <= t_now) and (t_now < schedule['to']):
                # within the timezone for this schedule
                schedrange = schedule['ranges']
                stepmode = schedule['stepmode']
                got_one = True
                break  # jump out the loop -- so the first matching timezone has priority over any others
        if not got_one:
            sys.exit('Fail: time=%5.2f not within any timezone in order_schedules=%s' % (t_now, order_schedules))
        return schedrange, stepmode

    n_buyers = trader_stats['n_buyers']
    n_sellers = trader_stats['n_sellers']

    shuffle_times = True

    cancellations = []

    if len(pending) < 1:
        # list of pending (to-be-issued) customer orders is empty, so generate a new one
        new_pending = []

        # demand side (buyers)
        issuetimes = getissuetimes(n_buyers, orders_sched['timemode'], orders_sched['interval'], shuffle_times, True)

        ordertype = 'Bid'
        (sched, mode) = getschedmode(time, orders_sched['dem'])
        for t in range(n_buyers):
            issuetime = time + issuetimes[t]
            tname = 'B%02d' % t
            orderprice = getorderprice(t, sched, n_buyers, mode, issuetime)
            order = Order(tname, ordertype, orderprice, 1, issuetime, chrono.time())
            new_pending.append(order)

        # supply side (sellers)
        issuetimes = getissuetimes(n_sellers, orders_sched['timemode'], orders_sched['interval'], shuffle_times, True)
        ordertype = 'Ask'
        (sched, mode) = getschedmode(time, orders_sched['sup'])
        for t in range(n_sellers):
            issuetime = time + issuetimes[t]
            tname = 'S%02d' % t
            orderprice = getorderprice(t, sched, n_sellers, mode, issuetime)
            # print('time %d sellerprice %d' % (time,orderprice))
            order = Order(tname, ordertype, orderprice, 1, issuetime, chrono.time())
            new_pending.append(order)
    else:
        # there are pending future orders: issue any whose timestamp is in the past
        new_pending = []
        for order in pending:
            if order.time < time:
                # this order should have been issued by now
                # issue it to the trader
                tname = order.tid
                response = traders[tname].add_order(order, vrbs)
                if vrbs:
                    print('Customer order: %s %s' % (response, order))
                if response == 'LOB_Cancel':
                    cancellations.append(tname)
                    if vrbs:
                        print('Cancellations: %s' % cancellations)
                # and then don't add it to new_pending (i.e., delete it)
            else:
                # this order stays on the pending list
                new_pending.append(order)
    return [new_pending, cancellations]


def market_session(sess_id, starttime, endtime, trader_spec, order_schedule, dumpfile_flags, sess_vrbs):
    """
    One session in the market.
    :param sess_id: the character-string ID for this session, used in naming output files.
    :param starttime: the time the session starts.
    :param endtime: the time the sessiom ends.
    :param trader_spec: specification of the traders populating the market for this session.
    :param order_schedule: specification of the "customer orders" assigned to traders, i.e. the supply/demand schedule.
    :param dumpfile_flags: a dictionary of Boolean flags specifying which output files to be written for this session.
    :param sess_vrbs: verbosity: if True, output a running commentary on what is going on; if False, stay silent.
    :return: <nothing>.
    """

    def dump_strats_frame(frametime, stratfile, trdrs):
        """
        Write one frame of strategy snapshot
        :param frametime: the time that the frame snapshot is printed.
        :param stratfile:  the file to write to.
        :param trdrs: the population of traders.
        :return: <nothing>
        """

        line_str = 't=,%.0f, ' % frametime

        best_buyer_id = None
        best_buyer_prof = 0
        best_buyer_strat = None
        best_seller_id = None
        best_seller_prof = 0
        best_seller_strat = None

        # loop through traders to find the best
        for trdr in traders:
            trader = trdrs[trdr]

            # print('PRSH/PRDE/ZIPSH strategy recording, t=%s' % trader)
            if trader.ttype == 'PRSH' or trader.ttype == 'PRDE' or trader.ttype == 'ZIPSH':
                line_str += 'id=,%s, %s,' % (trader.tid, trader.ttype)

                if trader.ttype == 'ZIPSH':
                    # we know that ZIPSH sorts the set of strats into best-first
                    act_strat = trader.strats[0]['stratvec']
                    act_prof = trader.strats[0]['pps']
                else:
                    act_strat = trader.strats[trader.active_strat]['stratval']
                    act_prof = trader.strats[trader.active_strat]['pps']

                line_str += 'actvstrat=,%s ' % trader.strat_csv_str(act_strat)
                line_str += 'actvprof=,%f, ' % act_prof

                if trader.tid[:1] == 'B':
                    # this trader is a buyer
                    if best_buyer_id is None or act_prof > best_buyer_prof:
                        best_buyer_id = trader.tid
                        best_buyer_strat = act_strat
                        best_buyer_prof = act_prof
                elif trader.tid[:1] == 'S':
                    # this trader is a seller
                    if best_seller_id is None or act_prof > best_seller_prof:
                        best_seller_id = trader.tid
                        best_seller_strat = act_strat
                        best_seller_prof = act_prof
                else:
                    # wtf?
                    sys.exit('unknown trader id type in market_session')

        if best_buyer_id is not None:
            line_str += 'best_B_id=,%s, best_B_prof=,%f, best_B_strat=, ' % (best_buyer_id, best_buyer_prof)
            line_str += traders[best_buyer_id].strat_csv_str(best_buyer_strat)

        if best_seller_id is not None:
            line_str += 'best_S_id=,%s, best_S_prof=,%f, best_S_strat=, ' % (best_seller_id, best_seller_prof)
            line_str += traders[best_seller_id].strat_csv_str(best_seller_strat)

        line_str += '\n'

        if verbose:
            print('line_str: %s' % line_str)
        stratfile.write(line_str)
        stratfile.flush()
        os.fsync(stratfile)

    def blotter_dump(session_id, trdrs):
        """
        Write the blotter for each trader.
        :param session_id: this market session's ID string (used for the filename).
        :param trdrs: the population of traders.
        :return: <nothing>
        """
        bdump = open(session_id+'_blotters.csv', 'w')
        for trdr in trdrs:
            bdump.write('%s, %d\n' % (trdrs[trdr].tid, len(trdrs[trdr].blotter)))
            for b in trdrs[trdr].blotter:
                bdump.write('%s, %s, %.3f, %d, %s, %s, %d\n'
                            % (traders[trdr].tid, b['type'], b['time'], b['price'], b['party1'], b['party2'], b['qty']))
        bdump.close()

    orders_verbose = False
    lob_verbose = False
    process_verbose = False
    respond_verbose = False
    bookkeep_verbose = False
    populate_verbose = True

    if dumpfile_flags['dump_strats']:
        strat_dump = open(sess_id + '_strats.csv', 'w')
    else:
        strat_dump = None

    if dumpfile_flags['dump_lobs']:
        lobframes = open(sess_id + '_LOB_frames.csv', 'w')
    else:
        lobframes = None

    if dumpfile_flags['dump_avgbals']:
        avg_bals = open(sess_id + '_avg_balance.csv', 'w')
    else:
        avg_bals = None
        
    if dumpfile_flags['dump_tape']:
        # NB writing transactions only -- not writing cancellations
        tape_dump = open(sess_id + '_tape.csv', 'w')
    else:
        tape_dump = None
        
    # initialise the exchange
    exchange = Exchange()

    # create a bunch of traders
    traders = {}
    trader_stats = populate_market(trader_spec, traders, True, populate_verbose)

    # timestep set so that can process all traders in one second
    # NB minimum interarrival time of customer orders may be much less than this!!
    timestep = 1.0 / float(trader_stats['n_buyers'] + trader_stats['n_sellers'] + trader_stats['n_proptraders'])

    session_duration = float(endtime - starttime)

    time = starttime

    pending_cust_orders = []

    if sess_vrbs:
        print('\n%s;  ' % sess_id)

    # frames_done is record of what frames we have printed data for thus far
    frames_done = set()

    while time < endtime:

        # how much time left, as a percentage?
        time_left = (endtime - time) / session_duration

        if verbose:
            print('\n\n%s; t=%08.2f (%4.1f/100) ' % (sess_id, time, time_left*100))

        [pending_cust_orders, kills] = customer_orders(time, traders, trader_stats,
                                                       order_schedule, pending_cust_orders, orders_verbose)

        # if any newly-issued customer orders mean quotes on the LOB need to be cancelled, kill them
        if len(kills) > 0:
            # if verbose : print('Kills: %s' % (kills))
            for kill in kills:
                # if verbose : print('lastquote=%s' % traders[kill].lastquote)
                if traders[kill].lastquote is not None:
                    # if verbose : print('Killing order %s' % (str(traders[kill].lastquote)))
                    # NB if exchange.del_order() third argument = None then cancellations not written to tape file.
                    # exchange.del_order(time, traders[kill].lastquote, tape_dump, sess_vrbs)
                    exchange.del_order(time, traders[kill].lastquote, None, sess_vrbs)

        # get a limit-order quote (or None) from a randomly chosen trader
        tid = list(traders.keys())[random.randint(0, len(traders) - 1)]

        order = traders[tid].getorder(time, time_left, exchange.publish_lob(time, lobframes, lob_verbose))
        if sess_vrbs:
            print('trader=%s order=%s' % (tid, order))

        if order is not None:
            if order.otype == 'Ask' and order.price < traders[tid].orders[0].price:
                sys.exit('Bad ask')
            if order.otype == 'Bid' and order.price > traders[tid].orders[0].price:
                sys.exit('Bad bid')
            # send order to exchange
            traders[tid].n_quotes = 1
            trade = exchange.process_order(time, order, tape_dump, process_verbose)
            if trade is not None:
                # trade occurred,
                # so the counterparties update order lists and blotters
                traders[trade['party1']].bookkeep(time, trade, order, bookkeep_verbose)
                traders[trade['party2']].bookkeep(time, trade, order, bookkeep_verbose)
                if dumpfile_flags['dump_avgbals']:
                    trade_stats(sess_id, traders, avg_bals, time, exchange.publish_lob(time, lobframes, lob_verbose))

            # traders respond to whatever happened
            lob = exchange.publish_lob(time, lobframes, lob_verbose)
            any_record_frame = False
            for t in traders:
                # NB respond just updates trader's internal variables
                # doesn't alter the LOB, so processing each trader in
                # sequence (rather than random/shuffle) isn't a problem
                record_frame = traders[t].respond(time, lob, trade, respond_verbose)
                if record_frame:
                    any_record_frame = True

            # log all the PRSH/PRDE/ZIPSH strategy info for this timestep?
            if any_record_frame and dumpfile_flags['dump_strats']:
                # print one more frame to strategy dumpfile
                dump_strats_frame(time, strat_dump, traders)
                # record that we've written this frame
                frames_done.add(int(time))

        time = time + timestep

    # session has ended

    # write trade_stats for this session (NB could use this to write end-of-session summary only)
    if dumpfile_flags['dump_avgbals']:
        trade_stats(sess_id, traders, avg_bals, time, exchange.publish_lob(time, lobframes, lob_verbose))
        avg_bals.close()

    if dumpfile_flags['dump_blotters']:
        # record the blotter for each trader
        blotter_dump(sess_id, traders)

    if dumpfile_flags['dump_strats']:
        strat_dump.close()

    if dumpfile_flags['dump_lobs']:
        lobframes.close()


#############################
# # Below here is where we set up and run a whole series of experiments

if __name__ == "__main__":

    price_offset_filename = 'offset_BTC_USD_20250211.csv'

    # if called from the command line with one argument, the first argument is the price offset filename
    if len(sys.argv) > 1:
        price_offset_filename = sys.argv[1]

    # set up common parameters for all market sessions
    # 1000 days is often good, but 3*365=1095, so may as well go for three years.
    n_days = 1
    hours_in_a_day = 24     # how many hours the exchange operates for in a working day (e.g. NYSE = 7.5)
    start_time = 0.0
    end_time = 60.0 * 60.0 * hours_in_a_day * n_days
    duration = end_time - start_time


    def schedule_offsetfn_read_file(filename, col_t, col_p, scale_factor=75):
        """
        Read in a CSV data-file for the supply/demand schedule time-varying price-offset value
        :param filename: the CSV file to read
        :param col_t: column in the CSV that has the time data
        :param col_p: column in the CSV that has the price data
        :param scale_factor: multiplier on prices
        :return: on offset value event-list: one item for each change in offset value
                -- each item is percentage time elapsed, followed by the new offset value at that time
        """
        
        vrbs = True
        
        # does two passes through the file
        # assumes data file is all for one date, sorted in time order, in correct format, etc. etc.
        rwd_csv = csv.reader(open(filename, 'r'))
        
        # first pass: get time & price events, find out how long session is, get min & max price
        minprice = None
        maxprice = None
        firsttimeobj = None
        timesincestart = 0
        priceevents = []
        
        first_row_is_header = True
        this_is_first_row = True
        this_is_first_data_row = True
        first_date = None
        
        for line in rwd_csv:
            
            if vrbs:
                print(line)
            
            if this_is_first_row and first_row_is_header:
                this_is_first_row = False
                this_is_first_data_row = True
                continue
                
            row_date = line[col_t][:10]
            
            if this_is_first_data_row:
                first_date = row_date
                this_is_first_data_row = False
                
            if row_date != first_date:
                continue
                
            time = line[col_t][11:19]
            if firsttimeobj is None:
                firsttimeobj = datetime.strptime(time, '%H:%M:%S')
                
            timeobj = datetime.strptime(time, '%H:%M:%S')
            
            price_str = line[col_p]
            # delete any commas so 1,000,000 becomes 1000000
            price_str_no_commas = price_str.replace(',', '')
            price = float(price_str_no_commas)
            
            if minprice is None or price < minprice:
                minprice = price
            if maxprice is None or price > maxprice:
                maxprice = price
            timesincestart = (timeobj - firsttimeobj).total_seconds()
            priceevents.append([timesincestart, price])
            
            if vrbs:
                print(row_date, time, timesincestart, price)
            
        # second pass: normalise times to fractions of entire time-series duration
        #              & normalise price range
        pricerange = maxprice - minprice
        endtime = float(timesincestart)
        offsetfn_eventlist = []
        for event in priceevents:
            # normalise price
            normld_price = (event[1] - minprice) / pricerange
            # clip
            normld_price = min(normld_price, 1.0)
            normld_price = max(0.0, normld_price)
            # scale & convert to integer cents
            price = int(round(normld_price * scale_factor))
            normld_event = [event[0] / endtime, price]
            if vrbs:
                print(normld_event)
            offsetfn_eventlist.append(normld_event)
        
        return offsetfn_eventlist


    def schedule_offsetfn_from_eventlist(time, params):
        """
        Returns a price offset-value for the current time, by reading from an offset event-list.
        :param time: the current time
        :param params: a list of parameter values...
            params[1] is the final time (the end-time) of the current session.
            params[2] is the offset event-list: one item for each change in offset value
                        -- each item is percentage time elapsed, followed by the new offset value at that time
        :return: integer price offset value
        """

        final_time = float(params[0])
        offset_events = params[1]
        # this is quite inefficient: on every call it walks the event-list
        percent_elapsed = time/final_time
        offset = None
        for event in offset_events:
            offset = event[1]
            if percent_elapsed < event[0]:
                break
        return offset


    def schedule_offsetfn_increasing_sinusoid(t, params):
        """
        Returns sinusoidal time-dependent price-offset, steadily increasing in frequency & amplitude
        :param t: time
        :param params: set of parameters for the offsetfn: this is empty-set for this offsetfn but nonempty in others
        :return: the time-dependent price offset at time t
        """
        if params is None:  # this test of params is here only to prevent PyCharm from warning about unused parameters
            pass
        scale = -7500
        multiplier = 7500000    # determines rate of increase of frequency and amplitude
        offset = ((scale * t) / multiplier) * (1 + math.sin((t*t)/(multiplier * math.pi)))
        return int(round(offset, 0))

    # Here is an example of how to use the offset function
    #
    # range1 = (10, 190, (schedule_offsetfn, args)) # args is the list of arguments to the function
    # range2 = (200, 300, (schedule_offsetfn, args))

    # Here is an example of how to switch from range1 to range2 and then back to range1,
    # introducing two "market shocks"
    # -- here the timings of the shocks are at 1/3 and 2/3 into the duration of the session.
    #
    # supply_schedule = [ {'from':start_time, 'to':duration/3, 'ranges':[range1], 'stepmode':'fixed'},
    #                     {'from':duration/3, 'to':2*duration/3, 'ranges':[range2], 'stepmode':'fixed'},
    #                     {'from':2*duration/3, 'to':end_time, 'ranges':[range1], 'stepmode':'fixed'}
    #                   ]

    offsetfn_events = None
    if price_offset_filename is not None:
        offsetfn_events = schedule_offsetfn_read_file(price_offset_filename, 0, 1)

    # supply schedule (defines the supply curve)
    range1 = (75, 110, (schedule_offsetfn_from_eventlist, [[end_time, offsetfn_events]]))
    supply_schedule = [{'from': start_time, 'to': end_time, 'ranges': [range1], 'stepmode': 'random'}]

    # demand schedule (defines the demand curve)
    range2 = (125, 90, (schedule_offsetfn_from_eventlist, [[end_time, offsetfn_events]]))
    demand_schedule = [{'from': start_time, 'to': end_time, 'ranges': [range2], 'stepmode': 'random'}]

    # new customer orders arrive at each trader approx once every order_interval seconds
    order_interval = 10

    # order schedule wraps up the supply/demand schedules and details of how customer orders/assignments are issued
    order_sched = {'sup': supply_schedule, 'dem': demand_schedule,
                   'interval': order_interval, 'timemode': 'drip-poisson'}

    # now run a sequence of trials, one session per trial

    # if verbose = True, print a running commentary describing what's going on.
    verbose = False

    # n_trials is how many trials (i.e. market sessions) to run in total
    n_trials = 1

    # n_recorded is how many trials (i.e. market sessions) to write full data-files for
    n_trials_recorded = 5

    trial = 1

    while trial < (n_trials+1):

        # create unique i.d. string for this trial
        trial_id = 'bse_d%03d_i%02d_%04d' % (n_days, order_interval, trial)

        # buyer_spec specifies the strategies played by buyers, and for each strategy how many such buyers to create
        buyers_spec = [('SHVR', 5), ('GVWY', 5), ('ZIC', 2), ('ZIP', 13)]
        #     ('PRZI', 5, {'s_min': -1.0, 's_max': +1.0})]

        # seller_spec specifies the strategies played by sellers, and for each strategy how many such sellers to create
        sellers_spec = buyers_spec

        # proptraders_spec specifies strategies played by proprietary-traders, and how many of each
        proptraders_spec = [('PT1', 1, {'bid_percent': 0.95, 'ask_delta': 7}), ('PT2', 1, {'n_past_trades': 25})]

        # trader_spec wraps up the specifications for the buyers, sellers, and proptraders
        traders_spec = {'sellers': sellers_spec, 'buyers': buyers_spec, 'proptraders': proptraders_spec}

        if trial > n_trials_recorded:
            # switch off recording of detailed data-files
            dump_flags = {'dump_blotters': False, 'dump_lobs': False, 'dump_strats': False,
                          'dump_avgbals': False, 'dump_tape': False}
        else:
            # we're still recording all the required data-files
            dump_flags = {'dump_blotters': True, 'dump_lobs': False, 'dump_strats': True,
                          'dump_avgbals': True, 'dump_tape': True}

        # simulate the market session
        market_session(trial_id, start_time, end_time, traders_spec, order_sched, dump_flags, verbose)

        trial = trial + 1

    # The code in comments below here is for illustration, in case you want to do an exhaustive sweep of all possible
    # combinations of some set of trading strategies: if its of no interest, it can be deleted.
    #
    # run a sequence of trials that exhaustively varies the ratio of four trader types
    # NB this has weakness of symmetric proportions on buyers/sellers -- combinatorics of varying that are quite nasty
    #
    # n_trader_types = 4
    # equal_ratio_n = 4
    # n_trials_per_ratio = 50
    #
    # n_traders = n_trader_types * equal_ratio_n
    #
    # fname = 'balances_%03d.csv' % equal_ratio_n
    #
    # tdump = open(fname, 'w')
    #
    # min_n = 1
    #
    # trialnumber = 1
    # trdr_1_n = min_n
    # while trdr_1_n <= n_traders:
    #     trdr_2_n = min_n
    #     while trdr_2_n <= n_traders - trdr_1_n:
    #         trdr_3_n = min_n
    #         while trdr_3_n <= n_traders - (trdr_1_n + trdr_2_n):
    #             trdr_4_n = n_traders - (trdr_1_n + trdr_2_n + trdr_3_n)
    #             if trdr_4_n >= min_n:
    #                 buyers_spec = [('GVWY', trdr_1_n), ('SHVR', trdr_2_n),
    #                                ('ZIC', trdr_3_n), ('ZIP', trdr_4_n)]
    #                 sellers_spec = buyers_spec
    #                 traders_spec = {'sellers': sellers_spec, 'buyers': buyers_spec}
    #                 # print buyers_spec
    #                 trial = 1
    #                 while trial <= n_trials_per_ratio:
    #                     trial_id = 'trial%07d' % trialnumber
    #                     market_session(trial_id, start_time, end_time, traders_spec,
    #                                    order_sched, tdump, False, True)
    #                     tdump.flush()
    #                     trial = trial + 1
    #                     trialnumber = trialnumber + 1
    #             trdr_3_n += 1
    #         trdr_2_n += 1
    #     trdr_1_n += 1
    # tdump.close()
    #
    # print(trialnumber)
