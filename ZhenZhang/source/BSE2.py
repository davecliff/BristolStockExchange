# -*- coding: utf-8 -*-
#
# BSE: The Bristol Stock Exchange
#
# Version 2.0Beta: Nov 20th, 2018.
# Version 1.4: August 30th, 2018.
# Version 1.3: July 21st, 2018.
# Version 1.2: November 17th, 2012.
#
# Copyright (c) 2012-2019, Dave Cliff
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
# operating on a very simple model of a limit order book (LOB) exchange
#
# major simplifications in this version:
#       (a) only one financial instrument being traded
#       (b) each trader can have max of one order per single orderbook.
#       (c) simply processes each order in sequence and republishes LOB to all traders
#           => no issues with exchange processing latency/delays or simultaneously issued orders.
#
# NB this code has been written to be readable/intelligible, not efficient!

# could import pylab here for graphing etc

import sys
import math
import random
import csv
from datetime import datetime

from BSE2_msg_classes import Assignment, Order, Exch_msg
from BSE_trader_agents import Trader_ISHV, Trader_Shaver,Trader_Giveaway,Trader_AA, Trader_Sniper, Trader_ZIC,Trader_ZIP,Trader_OAA #, Trader_IAAB
from IZIP_MLOFI import Trader_IZIP_MLOFI
from IAA_MLOFI import Trader_IAA_MLOFI
from Simple_MLOFI import Trader_Simple_MLOFI
from GDX import  Trader_GDX
from IGDX_MLOFI import Trader_IGDX_MLOFI
from IAA_NEW import Trader_IAA_NEW
from ZZISHV import Trader_ZZISHV

# from BSE2_unittests import test_all
# from BSE2_dev import proc_OXO proc_ICE


bse_sys_minprice = 1  # minimum price in the system, in cents/pennies
bse_sys_maxprice = 200  # maximum price in the system, in cents/pennies: Todo -- eliminate reliance on this
ticksize = 1  # minimum change in price, in cents/pennies



# Orderbook_half is one side of the book:
# The internal records of the exchange include the ID of the trader who issued the order, arrival time, etc.
# The externally published LOB aggregates and anonymizes these details.

class Orderbook_half:

        def __init__(self, booktype, worstprice):

                self.booktype = booktype

                def bid_equaltoorbetterthan(p1, p2, verbose):
                        if verbose: print("bid_equaltoorbetterthan: %d >= %d ?" % (p1, p2))
                        if p1 >= p2: return(True)
                        else: return(False)

                def ask_equaltoorbetterthan(p1, p2, verbose):
                        if verbose: print("ask_equaltoorbetterthan: %d <= %d ?" % (p1, p2))
                        if p1 <= p2: return(True)
                        else: return(False)

                # function for deciding whether price A is equal to or better than price B
                if self.booktype == 'Bid':
                        self.equaltoorbetterthan = bid_equaltoorbetterthan
                elif self.booktype == 'Ask':
                        self.equaltoorbetterthan = ask_equaltoorbetterthan
                else: sys.exit('Fail: Orderbook_half __init__ passed booktype=%s', str(booktype))

                # dictionary of live orders received, indexed by Order ID
                self.orders = {}
                # limit order book, exchange's internal list, ordered by price, with associated order info
                self.lob = []
                # anonymized LOB, aggregated list with only price/qty info: as published to market observers
                self.lob_anon = []
                # list of orders "resting" at the exchange, i.e. orders that persist for some time (e.g. AON, ICE)
                self.resting = []
                # On-Close & On-Open hold LIM & MKT orders that execute at market open and close (MOO, MOC, LOO, LOC)
                self.on_close = []
                self.on_open = []
                # OXO stores details of "other" for OSO and OCO orders
                self.oxo = []
                # summary stats
                # self.best_price = None
                self.worst_price = worstprice
                # self.n_orders = 0  # how many orders?
                # self.lob_depth = 0  # how many different prices on lob?


        def __str__(self):
                v = 'OB_H> '
                s = '\n' + v + self.booktype + '\n'
                s = s + v + 'Orders: '
                for oid in self.orders:
                        s = s + str(oid) + '=' + str(self.orders[oid]) + ' '
                s = s + '\n'
                s = s + v + 'LOB:\n'
                for row in self.lob:
                        s = s + '[P=%d,[' % row[0] # price
                        for order in row[1]:
                                s = s + '[T=%5.2f Q=%d %s OID:%d]' % (order[0], order[1], order[2], order[3])
                        s = s + ']]\n'
                s = s + v + 'LOB_anon' + str(self.lob_anon) + '\n'
                s = s + v + 'MOB:'
                s = s + '\n'

                return s


        def anonymize_lob(self, verbose):
                # anonymize a lob, strip out order details, format as a sorted list
                # sorting is best prices at the front (LHS) of the list
                self.lob_anon = []
                if self.booktype == 'Bid':
                        for price in sorted(self.lob, reverse=True):
                                qty = self.lob[price][0]
                                self.lob_anon.append([price, qty])
                elif self.booktype == 'Ask':
                        for price in sorted(self.lob):
                                qty = self.lob[price][0]
                                self.lob_anon.append([price, qty])
                else:
                        sys.exit('Fail: Orderbook_half __init__ passed booktype=%s', str(booktype))
                if verbose: print self.lob_anon


        def build_lob(self, verbose):
                # take a list of orders and build a limit-order-book (lob) from it
                # NB the exchange needs to know arrival times and trader-id associated with each order
                # returns lob as a list, sorted by price best to worst, orders at same price sorted by arrival time
                # also builds aggregated & anonymized version (just price/quantity, sorted, as a list) for publishing to traders

                # First builds lob as a dictionary indexed by price
                lob = {}
                for oid in self.orders:
                        order = self.orders.get(oid)
                        price = int(order.price)
                        if price in lob:
                                # update existing entry
                                qty = lob[price][0]
                                orderlist = lob[price][1]
                                orderlist.append([order.time, order.qty, order.tid, order.orderid])
                                lob[price] = [qty + order.qty, orderlist]
                        else:
                                # create a new dictionary entry
                                lob[price] = [order.qty, [[order.time, order.qty, order.tid, order.orderid]]]

                self.lob = []
                for price in lob:
                        orderlist = lob[price][1]
                        orderlist.sort() #orders are sorted by arrival time
                        self.lob.append([price, orderlist]) #appends only the price and the order-list
                # now sort by price: order depends on book type
                if self.booktype == 'Bid':
                        self.lob.sort(reverse=True)
                elif self.booktype == 'Ask':
                        self.lob.sort()
                else:
                        sys.exit('Fail: Orderbook_half __init__ passed booktype=%s', str(booktype))

                # create anonymized version of LOB for publication
                self.lob_anon = []
                if self.booktype == 'Bid':
                        for price in sorted(lob, reverse=True):
                                qty = lob[price][0]
                                self.lob_anon.append([price, qty])
                else:
                        for price in sorted(lob):
                                qty = lob[price][0]
                                self.lob_anon.append([price, qty])

                if verbose: print self.lob_anon

                # record best price and associated trader-id
                if len(self.lob) > 0 :
                        if self.booktype == 'Bid':
                                self.best_price = self.lob_anon[-1][0] #assumes reverse order COME BACK HERE
                        else :
                                self.best_price = self.lob_anon[0][0]
                else :
                        self.best_price = None

                if verbose: print self.lob


        def book_add(self, order, verbose):
                # add an order to the master list holding the orders
                if verbose: print('>book_add %s' % (order))
                self.orders[order.orderid] = order
                self.n_orders = len(self.orders)
                # reconstruct the LOB -- from scratch (inefficient)
                self.build_lob(verbose)
                return None #null response


        def book_CAN(self, time, order, pool_id, verbose):
                # delete (CANcel) an order from the dictionary holding the orders

                def add_tapeitem(eventlist, pool_id, time, oid, otype, qty, verbose):
                        # add_tapeitem(): add an event to list of events that will be written to tape
                        tape_event = {'pool_id':pool_id, 'type':'CAN', 'time':time, 'oid':oid, 'otype':otype, 'o_qty':qty}
                        eventlist.append(tape_event)
                        if verbose: print('book_CAN.add_tapeitem() trans_event=%s' % tape_event)

                tape_events=[]

                if verbose:
                        print('>OrderbookHalf.book_CAN %s' % order)
                        for ord in self.orders: print("{%s: %s}" % (ord,str(self.orders[ord])))

                oid = order.orderid
                if len(self.orders)>0 and (self.orders.get(oid) != None) :
                        if verbose: print('Deleting order %s' % oid)
                        o_qty = self.orders[oid].qty
                        o_type = self.booktype
                        del(self.orders[oid])
                        self.n_orders = len(self.orders)
                        # reconstruct the LOB -- from scratch (inefficient)
                        self.build_lob(verbose)
                        if verbose: print('<book_CAN %s' % self.orders)

                        tmsg = Exch_msg(order.tid, oid, "CAN", [], None, 0, 0)
                        add_tapeitem(tape_events, pool_id, time, oid, o_type, o_qty, verbose)

                        return {"TraderMsgs":[tmsg], "TapeEvents":tape_events}
                else:
                        print oid
                        print 'NOP' # no operation -- order ID not in the order dictionary
                        sys.exit('Fail: book_CAN() attempts to delete nonexistent order ')


        def book_take(self, time, order, pool_id, verbose):
                # process the order by taking orders off the LOB, consuming liquidity at the top of the book
                # this is where (MKT, IOC, FOK, AON) orders get matched and execute
                # returns messages re transactions, to be sent to traders involved; and a list of events to write to the tape
                # MKT order consumes the specified quantity, if available: partial fills allowed; ignores the price (so watch out for loss-making trades)
                # FOK only completes if it can consume the specified quantity at prices equal to or better than the specified price
                # IOC executes as much as it can of the specified quantity; allows partial fill: unfilled portion of order is cancelled
                # AON is like FOK but rests at the exchange until either (a) it can do complete fill or (b) clock reaches specified expiry time, at which point order cancelled.
                # NB the cancellations are not written to the tape, because they do not take liquidity away from the LOB


                def add_msg(msglist, tid, oid, etype, transactions, rev_order, fee, verbose):
                        # add_msg(): add a message to list of messages from exchange back to traders
                        # each msg tells trader [tid] that [OID] resulted in an event-type from [PART|FILL|FAIL]
                        # if PART then also sends back [revised order] -- telling the trader what the LOB retains as the unfilled portion
                        # if FILL then [revised order] is None
                        # message concludes with bank-balance details: exchange fee & trader's balance at exchange
                        msg = Exch_msg(tid, oid, etype, transactions, rev_order, fee, 0)
                        msglist.append(msg)
                        if verbose: print(msg)


                def add_tapeitem(eventlist, pool_id, eventtype, time, price, qty, party_from, party_to, verbose):
                        # add_tapeitem(): add an event to list of events that will be written to tape
                        # event type within book_take should be 'Trade'
                        tape_event = { 'pool_id': pool_id,
                                       'type': eventtype,
                                       'time': time,
                                       'price': price,
                                       'qty': qty,
                                       'party1': party_from,
                                       'party2': party_to}
                        eventlist.append(tape_event)
                        if verbose: print('add_tapeitem() tape_event=%s' % tape_event)


                msg_list = []           # details of orders consumed from the LOB when filling this order
                trnsctns = []           # details of transactions resulting from this incoming order walking the book
                tape_events = []        # details of transaction events to be written onto tape
                qty_filled = 0          # how much of this order have we filled so far?
                fee = 0               # exchange fee charged for processing this order (taking liquidity, wrt maker-taker)

                if verbose: print('>book_take(): order=%s, lob=%s' % (order, self.lob))


                # initial checks, return FAIL if there is simply no hope of executing this order

                if len(self.lob) == 0:
                        # no point going any further; LOB is empty
                        add_msg(msg_list, order.tid, order.orderid, "FAIL", [], None, fee, verbose)
                        return {"TraderMsgs": msg_list, "TapeEvents": tape_events}

                # how deep is the book? (i.e. what is cumulative qty available) at this order's indicated price level?
                depth = 0
                for level in self.lob_anon:
                        if self.equaltoorbetterthan(level[0], order.price, verbose):
                                depth += level[1]
                        else:  # we're past the level in the LOB where the prices are good for this order
                                break

                if order.ostyle == "FOK" or order.ostyle == "AON":
                        # FOK and AON require a complete fill
                        # so we first check that this order can in principle be filled: is there enough liquidity available?
                        if depth < order.qty:
                                # there is not enough depth at prices that allow this order to completely fill
                                add_msg(msg_list, order.tid, order.oid, "FAIL", [], None, fee, verbose)
                                # NB here book_take() sends a msg back that an AON order is FAIL, that needs to be picked up by the
                                # exchange logic and not passed back to the trader concerned, unless the AON has actually timed out
                                return {"TraderMsgs": msg_list, "TapeEvents": tape_events}

                if order.ostyle == "IOC" and depth < 1 :
                        # IOC order is a FAIL because there is no depth at all for the indicated price
                        add_msg(msg_list, order.tid, order.orderid, "FAIL", [], None, fee, verbose)
                        return {"TraderMsgs": msg_list, "TapeEvents": tape_events}


                # we only get this far if...
                # LOB is not empty
                # order is FOK or AON (complete fill only) --  we know there's enough depth to complete
                # order is MKT (allows partial fill, ignores prices, stops when indicated quantity is reached or LOB is empty)
                # order is IOC (allows partial fill, aims for indicated quantity but stops when price-limit is reached or LOB is empty) and LOB depth at price > 0

                if order.otype == "Bid":
                        tid_to = order.tid
                        oid_to = order.orderid
                elif order.otype == "Ask":
                        tid_from = order.tid
                        oid_from = order.orderid
                else: # this shouldn't happen
                        sys.exit('>book_take: order.otype=%s in book_take' % order.otype)

                # make a copy of the order-list and lobs as it initially stands
                # used for reconciling fills and when order is abandoned because it can't complete (e.g. FOK, AON)
                # initial_orders = self.orders

                # work this order by "walking the book"

                qty_remaining = order.qty

                best_lob_price = self.lob[0][0]

                good_price = True

                if order.ostyle != "MKT":
                        good_price = self.equaltoorbetterthan(best_lob_price, order.price, verbose)

                # this while loop consumes the top of the LOB while trying to fill the order
                while good_price and (qty_remaining > 0) and (len(self.orders)>0):

                        good_price = self.equaltoorbetterthan(self.lob[0][0], order.price, verbose)

                        if verbose:
                                print('BK_TAKE: qty_rem=%d; lob=%s; good_price=%s' % (qty_remaining, str(self.lob), good_price))
                                sys.stdout.flush()

                        if order.ostyle == "IOC" and (not good_price):
                                # current LOB best price is unacceptable for IOC
                                if verbose: print(
                                                'BK_TAKE: IOC breaks out of while loop (otype=%s best LOB price = %d; order price = %d)' %
                                                (order.otype, self.lob[0][0], order.price))
                                break  # out of the while loop

                        best_lob_price = self.lob[0][0]
                        best_lob_orders = self.lob[0][1]
                        best_lob_order = best_lob_orders[0]
                        best_lob_order_qty = best_lob_order[1]
                        best_lob_order_tid = best_lob_order[2]
                        best_lob_order_oid = best_lob_order[3]
                        if order.otype == "Bid":
                                tid_from = best_lob_order_tid
                                oid_from = best_lob_order_oid
                        elif order.otype == "Ask":
                                tid_to = best_lob_order_tid
                                oid_to = best_lob_order_oid

                        if verbose: print('BK_TAKE: best_lob _price=%d _order=%s qty=%d oid_from=%d oid_to=%d tid_from=%s tid_to=%s\n' %
                                          (best_lob_price, best_lob_order, best_lob_order_qty, oid_from, oid_to, tid_from, tid_to))


                        # walk the book: does this order consume current best order on book?
                        if best_lob_order_qty >= qty_remaining:

                                # incoming liquidity-taking order is completely filled by consuming some/all of best order on LOB
                                qty = qty_remaining
                                price = best_lob_price
                                qty_filled = qty_filled + qty
                                best_lob_order_qty = best_lob_order_qty - qty
                                # the incoming order is a complete fill
                                transaction = {"Price":price, "Qty":qty}
                                trnsctns.append(transaction)

                                # add a message to the list of outgoing messages from exch to traders
                                add_msg(msg_list, order.tid, order.orderid, "FILL", trnsctns, None, fee, verbose)

                                # add a record of this to the tape (NB this identifies both parties to the trade, so only do it once)
                                add_tapeitem(tape_events, pool_id, 'Trade', time, price, qty, tid_from, tid_to, verbose)

                                # so far have dealt with effect of match on incoming order
                                # now need to deal with effect of match on best order on LOB (the other side of the deal)
                                if best_lob_order_qty > 0:
                                        # the best LOB order is only partially consumed
                                        best_lob_order[1] = best_lob_order_qty
                                        best_lob_orders[0] = best_lob_order
                                        self.lob[0][1] = best_lob_orders
                                        self.orders[best_lob_order_oid].qty = best_lob_order_qty
                                        # The LOB order it matched against is only a partial fill
                                        add_msg(msg_list, best_lob_order_tid, best_lob_order_oid, "PART", [transaction], self.orders[best_lob_order_oid], fee, verbose)
                                        # add_tapeitem(tape_events, 'Trade', time, price, qty, tid_from, tid_to, verbose)
                                else:
                                        # the best LOB order is fully consumed: delete it from LOB
                                        del(best_lob_orders[0])
                                        del(self.orders[best_lob_order_oid])
                                        # The LOB order it matched against also complete
                                        add_msg(msg_list, best_lob_order_tid, best_lob_order_oid, "FILL", [transaction], None, fee, verbose)
                                        # add_tapeitem(tape_events, 'Trade', time, price, qty, tid_from, tid_to, verbose)
                                        # check: are there other remaining orders at this price?
                                        if len(best_lob_orders) > 0:
                                                # yes
                                                self.lob[0][1] = best_lob_orders
                                        else:
                                                # no
                                                del (self.lob[0])  # consumed the last order on the LOB at this price
                                qty_remaining = 0  # liquidity-taking all done
                        else:
                                # order is only partially filled by current best order, but current best LOB order is fully filled
                                # consume all the current best and repeat
                                qty = best_lob_order_qty
                                price = best_lob_price
                                qty_filled = qty_filled + qty
                                transaction = {"Price": price, "Qty": qty}
                                trnsctns.append(transaction)

                                # add a message to the list of outgoing messages from exch to traders
                                add_msg(msg_list, best_lob_order_tid, best_lob_order_oid, "FILL", [transaction], None, fee, verbose)

                                # add a record of this to the tape (NB this identifies both parties to the trade, so only do it once)
                                add_tapeitem(tape_events, pool_id, 'Trade', time, price, qty, tid_from, tid_to, verbose)

                                # the best LOB order is fully consumed: delete it from LOB and from order-list
                                del(self.orders[best_lob_order_oid])
                                del(best_lob_orders[0])

                                # check: are there other remaining orders at this price?
                                if len(best_lob_orders) > 0:
                                        # yes
                                        self.lob[0][1] = best_lob_orders
                                else:
                                        # no
                                        del (self.lob[0])  # consumed the last order on the LOB at this price

                                qty_remaining = qty_remaining - qty
                                if verbose: print('New LOB=%s orders=%s' % (str(self.lob), str(self.orders)))

                # main while loop ends here

                # when we get to here either...
                # the order completely filled by consuming the front of the book (which may have emptied the whole book)
                # or the whole book was consumed (and is now empty) without completely filling the order
                # or IOC consumed as much of the book's availability at the order's indicated price (good_price = False)

                if qty_remaining > 0 :
                        if qty_remaining == order.qty:
                                # this order is wholly unfilled: that's a FAIL (how did this get past the initial checks?)
                                add_msg(msg_list, order.tid, order.orderid, "FAIL", [], None, fee, verbose)
                        else:
                                # this liquidity-taking order only partially filled but ran out of usable LOB
                                order.qty = qty_remaining #revise the order quantity
                                add_msg(msg_list, order.tid, order.orderid, "PART", trnsctns, order, fee, verbose)
                                # add_tapeitem(tape_events, 'Trade', time, price, qty, tid_from, tid_to, verbose)

                if verbose:
                        print('<Orderbook_Half.book_take() TapeEvents=%s' % tape_events)
                        print('<Orderbook_Half.book_take() TraderMsgs=')
                        for msg in msg_list:
                                print('%s,' % str(msg))
                        print('\n')

                # rebuild the lob to reflect the adjusted order list
                self.build_lob(verbose)

                return {"TraderMsgs":msg_list, "TapeEvents":tape_events}



# Orderbook for a single instrument: list of bids and list of asks and methods to manipulate them

class Orderbook(Orderbook_half):


        def __init__(self, id_string):
                self.idstr = id_string          # give it a name
                self.bids = Orderbook_half('Bid', bse_sys_minprice)
                self.asks = Orderbook_half('Ask', bse_sys_maxprice)
                self.ob_tape = []               # tape of just this orderbook's activities (may be consolidated at Exchange level)
                self.last_trans_t = None        # time of last transaction
                self.last_trans_p = None        # price of last transaction
                self.last_trans_q = None        # quantity of last transaction


        def __str__(self):
                s = 'Orderbook:\n'
                s = s + 'Bids: %s \n' % str(self.bids)
                s = s + 'Asks: %s \n' % str(self.asks)
                s = s + 'Tape[-5:]: %s \n' % str(self.ob_tape[-5:])
                s = s + '\n'
                return s


        def midprice(self, bid_p, bid_q, ask_p, ask_q):
                # returns midprice as mean of best bid and best ask if both best bid & best ask exist
                # if only one best price exists, returns that as mid
                # if neither best price exists, returns None
                mprice = None
                if bid_q > 0 and ask_q == None :
                        mprice = bid_p
                elif ask_q > 0 and bid_q == None :
                        mprice = ask_p
                elif bid_q>0 and ask_q >0 :
                        mprice = ( bid_p + ask_p ) / 2.0
                return mprice


        def microprice(self, bid_p, bid_q, ask_p, ask_q):
                mprice = None
                if bid_q>0 and ask_q >0 :
                        tot_q = bid_q + ask_q
                        mprice = ( (bid_p * ask_q) + (ask_p * bid_q) ) / tot_q
                return mprice


        def add_lim_order(self, order, verbose):
                # add a LIM order to the LOB and update records
                if verbose: print('>add_lim_order: order.orderid=%d' % (order.orderid))
                if order.otype == 'Bid':
                        response=self.bids.book_add(order, verbose)
                        best_price = self.bids.lob_anon[0][0]
                        self.bids.best_price = best_price
                else:
                        response=self.asks.book_add(order, verbose)
                        best_price = self.asks.lob_anon[0][0]
                        self.asks.best_price = best_price
                return response


        def process_order_CAN(self, time, order, verbose):

                # cancel an existing order
                if verbose: print('>Orderbook.process_order_CAN order.orderid=%d' % order.orderid)

                if order.otype == 'Bid':
                        # cancel order from the bid book
                        response = self.bids.book_CAN(time, order, self.idstr, verbose)
                elif order.otype == 'Ask':
                        # cancel order from the ask book
                        response = self.asks.book_CAN(time, order, self.idstr, verbose)
                else:
                        # we should never get here
                        sys.exit('process_order_CAN() given neither Bid nor Ask')

                # response should be a message for the trader, and an event to write to the tape

                if verbose: print('PO_CAN %s' % response)

                return response


        def process_order_XXX(self, time, order, verbose):

                # cancel all orders on this orderbook that were issued by the trader that issued this order
                if verbose: print('>Orderbook.process_order_XXX order.orderid=%d' % order.orderid)

                tid = order.tid
                # need to sweep through all bids and and all asks and delete all orders from this trader

                responselist = []

                for bid_order in self.bids.orders:
                        if bid_order.tid == tid :
                                responselist.append(self.bids.book_CAN(time, order, verbose))

                for ask_order in self.asks.orders:
                        if ask_order.tid == tid:
                                responselist.append(self.asks.book_CAN(time, order, verbose))

                # responselist is handed back to caller level for them to unpack

                if verbose: print('PO_CAN %s' % responselist)

                return responselist


        def process_order_take(self, time, order, verbose):

                if verbose: print('> Orderbook.process_order_take order.orderid=%d' % order.orderid)

                if order.otype == 'Bid':
                        # this bid consumes from the top of the ask book
                        response = self.asks.book_take(time, order, self.idstr, verbose)
                elif order.otype == 'Ask':
                        # this ask consumes from the top of the bid book
                        response = self.bids.book_take(time, order, self.idstr, verbose)
                else:   # we should never get here
                        sys.exit('process_order_take() given neither Bid nor Ask')

                if verbose: print('OB.PO_take %s' % response)

                return response


        def process_order_LIM(self, time, order, verbose):

                # adds LIM and GFD orders -- GFD is just a time-limited LIM

                def process_LIM(order, verbose):
                        response = self.add_lim_order(order, verbose)

                        if verbose:
                                print('>process_order_LIM order.orderid=%d' % order.orderid)
                                print('Response: %s' % response)

                        return response

                oprice = order.price

                # does the LIM price cross the spread?

                if order.otype == 'Bid':
                        if len(self.asks.lob) > 0 and oprice >= self.asks.lob[0][0]:
                                # crosses: this LIM bid lifts the best ask, so treat as IOC
                                if verbose: print("Bid LIM $%s lifts best ask ($%s) =>IOC" % (oprice, self.asks.lob[0][0]))
                                order.ostyle = 'IOC'
                                response = self.process_order_take(time, order, verbose)
                        else:
                                response = process_LIM(order, verbose)

                elif order.otype == 'Ask':
                        if len(self.bids.lob) > 0 and oprice <= self.bids.lob[0][0]:
                                # crosses: this LIM ask hits the best bid, so treat as IOC
                                if verbose: print("Ask LIM $%s hits best bid ($%s) =>IOC" % (oprice, self.bids.lob[0][0]))
                                order.ostyle = 'IOC'
                                response = self.process_order_take(time, order, verbose)
                        else:
                                response = process_LIM(order, verbose)
                else:
                        # we should never get here
                        sys.exit('process_order_LIM() given neither Bid nor Ask')

                return response


        def process_order_pending(self, time, order, verbose):
                # this returns a null response because it just places the order on the relevant pending-execution list
                # order styles LOO and MOO are subsequently processed/executed in the market_open() method
                # order styles LOC and MOC are subsequently processed/executed in the market_close() method

                if order.ostyle == 'LOO' or order.ostyle == 'MOO':
                        if order.otype == 'Bid':
                                self.bids.on_open.append(order)
                        elif order.otype == 'Ask':
                                self.asks.on_open.append(order)
                        else:
                                # we should never get here
                                sys.exit('process_order_pending() LOO/MOO given neither Bid nor Ask')

                elif order.ostyle == 'LOC' or order.ostyle == 'MOC':
                        if order.otype == 'Bid':
                                self.bids.on_close.append(order)
                        elif order.otype == 'Ask':
                                self.asks.on_close.append(order)
                        else:
                                # we should never get here
                                sys.exit('process_order_pending() LOC/MOC given neither Bid nor Ask')

                else: sys.exit('process_order_pending() given something other than LOO MOO LOC MOC')

                return {'TraderMsgs':None, 'TapeEvents':None}



# Exchange's internal orderbooks

class Exchange(Orderbook):


        def __init__(self, eid):
                self.eid = eid          # exchange ID string
                self.lit = Orderbook(eid + "Lit")  # traditional lit exchange
                self.drk = Orderbook(eid + "Drk")  # NB just a placeholder -- in this version of BSE the dark pool is undefined
                self.tape = []          # tape: consolidated record of trading events on the exchange
                self.trader_recs = {}   # trader records (balances from fees, reputations, etc), indexed by traderID
                self.order_id = 0       # unique ID code for each order received by the exchange, starts at zero
                self.open = False       # is the exchange open (for business) or closed?


        def __str__(self):
                s = '\nExchID: %s ' % (self.eid)
                if self.open: s = s + '(Open)\n'
                else: s = s + '(Closed)\n'
                s = s + 'Lit ' + str(self.lit)
                s = s + 'Dark ' + str(self.drk)
                s = s + 'OID: %d; ' % self.order_id
                s = s + 'TraderRecs: %s' % self.trader_recs
                s = s + 'Tape[-4:]: %s' % self.tape[-4:]
                s = s + '\n'
                return s


        class trader_record:
                # exchange's records for an individual trader

                def __init__(self, time, tid):
                        self.tid = tid          # this trader's ID
                        self.regtime = time     # time when first registered
                        self.balance = 0        # balance at the exchange (from exchange fees and rebates)
                        self.reputation = None  # reputation -- FOR GEORGE CHURCH todo -- integrate with George's work
                        self.orders = []        # list of orders received from this trader
                        self.msgs = []          # list of messages sent to this trader


                def __str__(self):
                        s = '[%s bal=%d rep=%s orders=%s msgs=%s]' % (self.tid, self.balance, self.reputation, self.orders, self.msgs)
                        return s


        def consolidate_responses(self, responses):

                consolidated = {'TraderMsgs':[], 'TapeEvents':[]}

                if len(responses) > 1:
                        # only need to do this if been given more than one response
                        for resp in responses:
                                consolidated['TraderMsgs'].append(resp['TraderMsgs'])
                                consolidated['TapeEvents'].append(resp['TapeEvents'])
                        # could sort into time-order here, but its not essential -- todo
                else:
                        consolidated = responses[0]

                return consolidated


        def mkt_open(self, time, verbose):

                # exchange opens for business
                # need to process any LOO and MOO orders:
                # processes LOO and MOO orders in sequence wrt where they are in the relevant on_open list

                def open_pool(time, pool, verbose):

                        responses = []

                        # LOO and MOO
                        for order in pool.on_open:
                                if order.ostyle == 'LIM':
                                        responses.append(pool.process_order_LIM(time, order, verbose))
                                elif order.ostyle == 'MKT':
                                        responses.append(pool.process_order_take(time, order, verbose))
                                else: sys.exit('FAIL in open_pool(): neither LIM nor MKT in on_open list ')

                        return responses


                print('Exchange %s opening for business', self.eid)
                response_l = open_pool(self.lit)
                response_d = open_pool(self.drk)

                self.open = True
                return consolidate_responses([response_l, response_d])


        def mkt_close(self):

                # exchange closes for business
                # need to process any LOC, MOC, and GFD orders
                # NB GFD orders assumes that exchange closing is the same as end of day

                def close_pool(time, pool, verbose):

                        responses = []

                        # LOC and MOC
                        for order in pool.on_close:
                                if order.ostyle == 'LIM':
                                        responses.append(pool.process_order_LIM(time, order, verbose))
                                elif order.ostyle == 'MKT':
                                        responses.append(pool.process_order_take(time, order, verbose))
                                else: sys.exit('FAIL in open_pool(): neither LIM nor MKT in on_close list ')
                        # GFD  -- cancel any orders still on the books
                        for order in pool.orders:
                                if order.ostyle == 'GFD':
                                        responses.append(pool.process_order_CAN(time, order, verbose))

                        return responses

                print('Exchange %s closing for business', self.eid)
                response_l = close_pool(self.lit)
                response_d = close_pool(self.drk)

                self.open = False
                return consolidate_responses([response_l, response_d])


        def tape_update(self, tr, verbose):

                # updates the tape
                if verbose: print("Tape update: tr=%s; len(tape)=%d tape[-3:]=%s" % (tr, len(self.tape), self.tape[-3:]))

                self.tape.append(tr)

                if tr['type'] == 'Trade':
                        # process the trade
                        if verbose: print('>>>>>>>>TRADE t=%5.3f $%d Q%d %s %s\n' %
                                          (tr['time'], tr['price'], tr['qty'], tr['party1'], tr['party2']))
                        self.last_trans_t = tr['time']  # time of last transaction
                        self.last_trans_p = tr['price']  # price of last transaction
                        self.last_trans_q = tr['qty']  # quantity of last transaction
                        return tr


        def dump_tape(self, session_id, dumpfile, tmode,traders):

                # print('Dumping tape s.tape=')
                # for ti in self.tape:
                #         print('%s' % ti)

                for tapeitem in self.tape:
                        # print('tape_dump: tapitem=%s' % tapeitem)
                        if tapeitem['type'] == 'Trade':
                                dumpfile.write('%s, %s, %s,%s,%s,%s,%s, %s\n' % (session_id, tapeitem['pool_id'], tapeitem['time'], tapeitem['price'],tapeitem['qty'],traders[tapeitem['party2']].ttype, traders[tapeitem['party1']].ttype,str(tapeitem)))

                if tmode == 'wipe':
                        self.tape = []

                aaFile = open('myFile_AA.csv','a');

                for tapeitem in self.tape:
                        # print('tape_dump: tapitem=%s' % tapeitem)
                        if tapeitem['type'] == 'Trade':
                                if(traders[tapeitem['party2']].ttype == 'SHVR' and traders[tapeitem['party1']].ttype == 'AA'):
                                        aaFile.write('%s\n' % (tapeitem['price']))

                aaFile.close()

                iaaFile = open('myFile_IAA.csv','a')

                for tapeitem in self.tape:
                        # print('tape_dump: tapitem=%s' % tapeitem)
                        if tapeitem['type'] == 'Trade':
                                if (traders[tapeitem['party2']].ttype == 'SHVR' and traders[tapeitem['party1']].ttype == 'IAA'):
                                        iaaFile.write('%s\n' % (tapeitem['price']))

                iaaFile.close()





        def process_order(self, time, order, verbose):
                # process the order passed in as a parameter
                # number of allowable order-types is significantly expanded in BSE2 (previously just had LIM/MKT functionality)
                # BSE2 added order types such as FOK, ICE, etc
                # also added stub logic for larger orders to be routed to dark pool
                # currently treats dark pool as another instance of Orderbook, same as lit pool
                # incoming order has order ID assigned by exchange
                # return is {'tape_summary':... ,'trader_msgs':...}, explained further below

                if verbose: print('>Exchange.process_order()\n')

                trader_id = order.tid

                if not trader_id in self.trader_recs:
                        # we've not seen this trader before, so create a record for it
                        if verbose: print('t=%f: Exchange %s registering Trader %s:' % (time, self.eid, trader_id))
                        trader_rec = self.trader_record(time, trader_id)
                        self.trader_recs[trader_id] = trader_rec
                        if verbose: print('record= %s' % str(trader_rec))

                # what quantity qualifies as a block trade (route to DARK)?
                block_size = 300

                ostyle = order.ostyle

                ack_response = Exch_msg(trader_id, order.orderid, 'ACK', [[order.price, order.qty]],  None, 0, 0)
                if verbose: print ack_response


                # which pool does it get sent to: Lit or Dark?
                if order.qty < block_size:
                        if verbose: print('Process_order: qty=%d routes to LIT pool' % order.qty)
                        pool = self.lit
                else:
                        if verbose: print('Process_order: qty=%d routes to DARK pool' % order.qty)
                        pool = self.drk


                # Cancellations don't generate new order-ids

                if ostyle == 'CAN':
                        # deleting a single existing order
                        # NB this trusts the order.qty -- sends CANcel only to the pool that the QTY indicates
                        response = pool.process_order_CAN(time, order, verbose)

                elif ostyle == 'XXX':
                        # delete all orders from the trader that issued the XXX order
                        # need to sweep through both pools
                        response_l = self.lit.process_order_XXX(time, order, verbose)
                        response_d = self.drk.process_order_XXX(time, order, verbose)
                        # the response from either lit and/or dark might be a string of responses from multiple individual CAN orders
                        # here we just glue those together for later processing
                        self.consolidate_responses([response_l, response_d])

                else:
                        # give each new order a unique ID
                        order.orderid = self.order_id
                        self.order_id = order.orderid + 1

                        ack_msg = Exch_msg(trader_id, order.orderid, 'ACK', [[order.price, order.qty]], None, 0, 0)

                        if verbose: print('OrderID:%d, ack:%s\n' % (order.orderid, ack_msg))

                        if ostyle == 'LIM' or ostyle == 'GFD':
                                # GFD is just a LIM order with an expiry time
                                response = pool.process_order_LIM(time, order, verbose)

                        elif ostyle == 'MKT' or ostyle == 'AON' or ostyle == 'FOK' or ostyle == 'IOC':
                                if ostyle == 'AON': pool.resting.append(order) # put it on the list of resting orders
                                response = pool.process_order_take(time, order, verbose)
                                # AON is a special case: if current response is that it FAILed, but has not timed out
                                #                        then ignore the failure
                                # and if it didn't fail, check to remove it from the MOB
                                if ostyle == 'AON':
                                        if response['TraderMsgs'].event == 'FAIL':
                                                # it failed, but has it timed out yet?
                                                if time < order.styleparams['ExpiryTime']:
                                                        # it hasn't expired yet
                                                        # nothing to say back to the trader, nothing to write to tape
                                                        response['TraderMsgs'] = None
                                                        response['TapeEvents'] = None
                                        else:   # AON order executed successfully, remove it from the MOB
                                                pool.resting.remove(order)

                        elif ostyle == 'LOC' or ostyle == 'MOC' or ostyle == 'LOO' or ostyle == 'MOO':
                                # these are just placed on the relevant wait-list at the exchange
                                # and then processed by mkt_open() or mkt_close()
                                response = pool.process_order_pending(time, order, verbose)

                        elif ostyle == 'OCO' or ostyle == 'OSO':
                                # processing of OSO and OCO orders is a recursive call of this method
                                # that is, call process_order() on the first order in the OXO pair
                                # then call or ignore the second order depending on outcome of the first
                                # OCO and OSO are both defined via the following syntax...
                                # ostyle=OSO or OCO; styleparams=[[order1], [order2]]
                                # currently only defined for [order1] and [order2] both LIM type

                                if len(order.styleparams) == 2:
                                        order1 = order.styleparams[0]
                                        order2 = order.styleparams[1]
                                        if order1.ostyle == 'LIM' and order2.ostyle == 'LIM':
                                                sys.exit('Give up')

                                response = pool.process_order_OXO(time, order, verbose)

                        elif ostyle == 'ICE':
                                # this boils down to a chain of successively refreshed OSO orders, until its all used up
                                # so underneath it's LIM functionality only
                                response = pool.process_order_ICE(time, order, verbose)

                        else:
                                sys.exit('FAIL: process_order given order style %s', ostyle)




                if verbose: print ('<Exch.Proc.Order(): Order=%s; Response=%s' % (order, response))

                # default return values
                trader_msgs = None
                tape_events = None

                if response != None:
                        # non-null response should be dictionary with two items: list of trader messages and list of tape events
                        if verbose: print('Response ---- ')
                        trader_msgs = response["TraderMsgs"]
                        tape_events = response["TapeEvents"]

                        total_fees = 0
                        # trader messages include details of fees charged by exchange for processing this order
                        for msg in trader_msgs:
                                if msg.tid == trader_id:
                                        total_fees += msg.fee
                                        if verbose: print('Trader %s adding fee %d from msg %s' % (trader_id, msg.fee, msg))
                        self.trader_recs[trader_id].balance += total_fees
                        if verbose: print('Trader %s Exch %s: updated balance=%d' % (trader_id, self.eid, self.trader_recs[trader_id].balance))

                        # record the tape events on the tape
                        if len(tape_events) > 0:
                                for event in tape_events:
                                        self.tape_update(event, verbose)

                        if verbose:
                                print('<Exch.Proc.Order(): tape_events=%s' % tape_events)
                                s = '<Exch.Proc.Order(): trader_msgs=['
                                for msg in trader_msgs:
                                        s = s + '[' + str(msg) + '], '
                                s = s + ']'
                                print(s)

                        # by this point, tape has been updated
                        # so in principle only thing process_order hands back to calling level is messages for traders

                        # but...

                        # for back-compatibility with this method in BSE1.x and with trader definitions (AA, ZIP, etc)
                        # we ALSO hand back a "transaction record" which summarises any actual transactions
                        # or is None if no transactions occurred. Structure was:
                        # transaction_record = {'type': 'Trade',
                        #                       'time': time,
                        #                       'price': price,
                        #                       'party1': counterparty,
                        #                       'party2': order.tid,
                        #                       'qty': order.qty
                        #                       }
                        # In BSE 1.x the maximum order-size was Qty=1, which kept things very simple
                        # In BSE 2.x, a single order of Qty>1 can result in multiple separate transactions,
                        # so we need to aggregate those into one order. Do this by computing total cost C of
                        # execution for quantity Q and then declaring that the price for each unit was C/Q
                        # As there may now be more then one counterparty to a single order, party1 & party2 returned as None

                        tape_summary = None
                        if len(tape_events) > 0:
                                total_cost = 0
                                total_qty = 0
                                if verbose: print('tape_summary:')
                                for event in tape_events:
                                        if event['type'] == 'Trade':
                                                total_cost += event['price']
                                                total_qty += event['qty']
                                                if verbose: print('total_cost=%d; total_qty=%d' % (total_cost, total_qty))
                                if total_qty > 0 :
                                        avg_cost = total_cost / total_qty
                                        if verbose: print('avg_cost=%d' % avg_cost)
                                        tape_summary = {'type': 'Trade',
                                                        'time': time,
                                                        'price': avg_cost,
                                                        'party1': None,
                                                        'party2': None,
                                                        'qty': total_qty}

                        return {'tape_summary':tape_summary, 'trader_msgs':trader_msgs}
                else: return {'tape_summary':None, 'trader_msgs':None}


        # this returns the LOB data "published" by the exchange,
        # only applies to the lit book -- dark pools aren't published
        def publish_lob(self, time, tape_depth, verbose):

                n_bids = len(self.lit.bids.orders)
                if n_bids > 0 :
                        best_bid_p = self.lit.bids.lob_anon[0][0]
                else:   best_bid_p = None

                n_asks = len(self.lit.asks.orders)
                if n_asks > 0:
                        best_ask_p = self.lit.asks.lob_anon[0][0]
                else:
                        best_ask_p = None

                public_data = {}
                public_data['time'] = time
                public_data['bids'] = {'bestp':best_bid_p,
                                     'worstp':self.lit.bids.worst_price,
                                     'n': n_bids,
                                     'lob':self.lit.bids.lob_anon}
                public_data['asks'] = {'bestp':best_ask_p,
                                     'worstp':self.lit.asks.worst_price,
                                     'n': n_asks,
                                     'lob':self.lit.asks.lob_anon}

                public_data['last_t'] = self.lit.last_trans_t
                public_data['last_p'] = self.lit.last_trans_p
                public_data['last_q'] = self.lit.last_trans_q




                if tape_depth == None :
                        public_data['tape'] = self.tape                 # the full thing
                else:
                        public_data['tape'] = self.tape[-tape_depth:]   # depth-limited

                public_data['midprice'] = None
                public_data['microprice'] = None
                if n_bids>0 and n_asks>0 :
                        # neither side of the LOB is empty
                        best_bid_q= self.lit.bids.lob_anon[0][1]
                        best_ask_q = self.lit.asks.lob_anon[0][1]
                        public_data['midprice'] = self.lit.midprice(best_bid_p, best_bid_q, best_ask_p, best_ask_q)
                        public_data['microprice'] = self.lit.microprice(best_bid_p, best_bid_q, best_ask_p, best_ask_q)

                if verbose:
                        print('Exchange.publish_lob: t=%s' % time)
                        print('BID_lob=%s' % public_data['bids']['lob'])
                        print('best=%s; worst=%s; n=%s ' % (best_bid_p, self.lit.bids.worst_price, n_bids))
                        print(str(self.lit.bids))
                        print('ASK_lob=%s' % public_data['asks']['lob'])
                        print('best=%s; worst=%s; n=%s ' % (best_ask_p, self.lit.asks.worst_price, n_asks))
                        print(str(self.lit.asks))
                        print('Midprice=%s; Microprice=%s' % (public_data['midprice'], public_data['microprice']))
                        print('Last transaction: time=%s; price=%s; qty=%s' % (public_data['last_t'],public_data['last_p'],public_data['last_q']))
                        print('tape[-3:]=%s'% public_data['tape'][-3:])
                        sys.stdout.flush()


                return public_data







##########################---Below lies the experiment/test-rig---##################



# trade_stats()
# dump CSV statistics on exchange data and trader population to file for later analysis
# this makes no assumptions about the number of types of traders, or
# the number of traders of any one type -- allows either/both to change
# between successive calls, but that does make it inefficient as it has to
# re-analyse the entire set of traders on each call
def trade_stats(expid, traders, dumpfile, time, lob):
        trader_types = {}
        n_traders = len(traders)
        for t in traders:
                ttype = traders[t].ttype
                if ttype in trader_types.keys():
                        t_balance = trader_types[ttype]['balance_sum'] + traders[t].balance
                        n = trader_types[ttype]['n'] + 1
                else:
                        t_balance = traders[t].balance
                        n = 1
                trader_types[ttype] = {'n':n, 'balance_sum':t_balance}


        dumpfile.write('%s, %06d, ' % (expid, time))
        for ttype in sorted(list(trader_types.keys())):
                n = trader_types[ttype]['n']
                s = trader_types[ttype]['balance_sum']
                dumpfile.write('%s, %d, %d, %f, ' % (ttype, s, n, s / float(n)))

        if lob['bids']['bestp'] != None :
                dumpfile.write('%d, ' % (lob['bids']['bestp']))
        else:
                dumpfile.write('N, ')
        if lob['asks']['bestp'] != None :
                dumpfile.write('%d, ' % (lob['asks']['bestp']))
        else:
                dumpfile.write('N, ')
        dumpfile.write('\n');



# create a bunch of traders from traders_spec
# returns tuple (n_buyers, n_sellers)
# optionally shuffles the pack of buyers and the pack of sellers
def populate_market(traders_spec, traders, shuffle, verbose):


        def trader_type(robottype, name):
                if robottype == 'GVWY':
                        return Trader_Giveaway('GVWY', name, 0.00, 0)
                elif robottype == 'ZIC':
                        return Trader_ZIC('ZIC', name, 0.00, 0)
                elif robottype == 'SHVR':
                        return Trader_Shaver('SHVR', name, 0.00, 0)
                elif robottype == 'ISHV':
                        return Trader_ISHV('ISHV', name, 0.00, 0)
                elif robottype == 'SNPR':
                        return Trader_Sniper('SNPR', name, 0.00, 0)
                elif robottype == 'ZIP':
                        return Trader_ZIP('ZIP', name, 0.00, 0)
                elif robottype == 'AA':
                        return Trader_AA('AA', name, 0.00, 0)

                elif robottype == 'AAA':
                        return Trader_AA('AAA', name, 0.00, 0)


                elif robottype == 'SIMPLE':
                        return Trader_Simple_MLOFI('SIMPLE',name,0.00,0)
                elif robottype == 'IAA_MLOFI_ASK':
                        return Trader_IAA_MLOFI('MLOFI_ASK',name,0.00,0)
                elif robottype == 'IAA_MLOFI_BID':
                        return Trader_IAA_MLOFI('MLOFI_BID',name,0.00,0)
                elif robottype == 'AAAA':
                        return Trader_AA('AAAA', name, 0.00, 0)

                elif robottype == 'ISHV_ASK':
                        return Trader_ISHV('ISHV_ASK', name, 0.00, 0)
                elif robottype == 'GDX':
                        return Trader_GDX('GDX', name, 0.00, 0)
                elif robottype == 'GDXB':
                        return Trader_GDX('GDXB', name, 0.00, 0)
                elif robottype == 'ZIPP':
                        return Trader_ZIP('ZIPP', name, 0.00, 0)

                elif robottype == 'IAA_MLOFI':
                        return Trader_IAA_MLOFI('MLOFI',name,0.00,0,3)
                elif robottype == 'IAA_MLOFI1':
                        return Trader_IAA_MLOFI('MLOFI1',name,0.00,0, 1)

                elif robottype == 'IAA_MLOFI2':
                        return Trader_IAA_MLOFI('MLOFI2', name, 0.00,0, 2)
                elif robottype == 'IAA_MLOFI3':
                        return Trader_IAA_MLOFI('MLOFI3', name, 0.00,0, 3)
                elif robottype == 'IAA_MLOFI4':
                        return Trader_IAA_MLOFI('MLOFI4', name, 0.00, 0,4)
                elif robottype == 'IAA_MLOFI5':
                        return Trader_IAA_MLOFI('MLOFI5', name, 0.00,0, 5)
                elif robottype == 'IAA_MLOFI6':
                        return Trader_IAA_MLOFI('MLOFI6', name, 0.00,0, 6)
                elif robottype == 'IAA_MLOFI7':
                        return Trader_IAA_MLOFI('MLOFI7', name, 0.00,0, 7)
                elif robottype == 'IAA_MLOFI8':
                        return Trader_IAA_MLOFI('MLOFI8', name, 0.00,0, 8)
                elif robottype == 'IAA_MLOFI9':
                        return Trader_IAA_MLOFI('MLOFI9', name, 0.00,0, 9)
                elif robottype == 'IAA_MLOFI10':
                        return Trader_IAA_MLOFI('MLOFI10', name, 0.00, 0, 10)
                elif robottype == 'IAA_MLOFI11':
                        return Trader_IAA_MLOFI('MLOFI11', name, 0.00, 0, 11)
                elif robottype == 'IAA_MLOFI12':
                        return Trader_IAA_MLOFI('MLOFI12', name, 0.00, 0, 12)
                elif robottype == 'IAA_MLOFI13':
                        return Trader_IAA_MLOFI('MLOFI13', name, 0.00, 0, 13)
                elif robottype == 'IAA_MLOFI14':
                        return Trader_IAA_MLOFI('MLOFI14', name, 0.00, 0, 14)
                elif robottype == 'IAA_MLOFI15':
                        return Trader_IAA_MLOFI('MLOFI15', name, 0.00, 0, 15)
                elif robottype == 'IAA_MLOFI16':
                        return Trader_IAA_MLOFI('MLOFI16', name, 0.00, 0, 16)
                elif robottype == 'IAA_MLOFI17':
                        return Trader_IAA_MLOFI('MLOFI17', name, 0.00, 0, 17)
                elif robottype == 'IAA_MLOFI18':
                        return Trader_IAA_MLOFI('MLOFI18', name, 0.00, 0, 18)
                elif robottype == 'IAA_MLOFI19':
                        return Trader_IAA_MLOFI('MLOFI19', name, 0.00, 0, 19)
                elif robottype == 'IAA_MLOFI20':
                        return Trader_IAA_MLOFI('MLOFI20', name, 0.00, 0, 20)
                elif robottype == 'IAA_MLOFI30':
                        return Trader_IAA_MLOFI('MLOFI30', name, 0.00, 0, 30)
                elif robottype == 'IAA_MLOFI50':
                        return Trader_IAA_MLOFI('MLOFI50', name, 0.00, 0, 50)
                elif robottype == 'IZIP_3':
                        return Trader_IZIP_MLOFI('IZIP_3',name,0.00,0,3)

                elif robottype == 'IGDX_3':
                        return Trader_IGDX_MLOFI('IGDX_3', name, 0.00, 0, 3)
                elif robottype == 'IZIPB_3':
                        return Trader_IZIP_MLOFI('IZIPB_3',name,0.00,0,3)

                elif robottype == 'IGDXB_3':
                        return Trader_IGDX_MLOFI('IGDXB_3', name, 0.00, 0, 3)
                elif robottype == 'IAAB_3':
                        return Trader_IAA_MLOFI('IAAB3', name, 0.00,0, 3)


                elif robottype == 'ASK_IGDX_3':
                        return Trader_IGDX_MLOFI('ASK_IGDX_3', name, 0.00, 0, 3)
                elif robottype == 'BID_IGDX_3':
                        return Trader_IGDX_MLOFI('BID_IGDX_3', name, 0.00, 0, 3)
                elif robottype == 'ASK_IZIP_3':
                        return Trader_IZIP_MLOFI('ASK_IZIP_3',name,0.00,0,3)
                elif robottype == 'BID_IZIP_3':
                        return Trader_IZIP_MLOFI('BID_IZIP_3',name,0.00,0,3)
                elif robottype == 'ASK_IAA_3':
                        return Trader_IAA_MLOFI('ASK_IAA_3', name, 0.00,0, 3)
                elif robottype == 'BID_IAA_3':
                        return Trader_IAA_MLOFI('BID_IAA_3', name, 0.00, 0, 3)

                elif robottype == 'ASK_AA':
                        return Trader_AA('ASK_AA', name, 0.00, 0)
                elif robottype == 'BID_AA':
                        return Trader_AA('BID_AA', name, 0.00, 0)
                elif robottype == 'ASK_GDX':
                        return Trader_GDX('ASK_GDX', name, 0.00, 0)
                elif robottype == 'BID_GDX':
                        return Trader_GDX('BID_GDX', name, 0.00, 0)
                elif robottype == 'ASK_ZIP':
                        return Trader_ZIP('ASK_ZIP', name, 0.00, 0)
                elif robottype == 'BID_ZIP':
                        return Trader_ZIP('BID_ZIP', name, 0.00, 0)


                elif robottype == 'IAA':
                        return Trader_IAA_MLOFI('IAA', name, 0.00,0, 3)
                elif robottype == 'IAA_3':
                        return Trader_IAA_MLOFI('IAA_3', name, 0.00,0, 3)


                elif robottype == 'ASK_SHVR':
                        return Trader_Shaver('ASK_SHVR', name, 0.00, 0)
                elif robottype == 'BID_SHVR':
                        return Trader_Shaver('BID_SHVR', name, 0.00, 0)
                elif robottype == 'ASK_ISHV_3':
                        return Trader_ISHV('ASK_ISHV_3', name, 0.00, 0)
                elif robottype == 'BID_ISHV_3':
                        return Trader_ISHV('BID_ISHV_3', name, 0.00, 0)


                elif robottype == 'GDXXX':
                        return Trader_GDX('GDXXX', name, 0.00, 0)
                elif robottype == 'GDXX':
                        return Trader_GDX('GDXX', name, 0.00, 0)



                elif robottype == 'IAA_NEW':
                        return Trader_IAA_NEW('IAA_NEW', name, 0.00, 0, 3)


                elif robottype == 'ZZISHV':
                        return Trader_ZZISHV('ZZISHV', name, 0.00, 0,3)
                elif robottype == 'ASK_ZZISHV':
                        return Trader_ZZISHV('ASK_ZZISHV', name, 0.00, 0,3)
                elif robottype == 'BID_ZZISHV':
                        return Trader_ZZISHV('BID_ZZISHV', name, 0.00, 0,3)
                elif robottype == 'ASK_ISHV':
                        return Trader_ISHV('ASK_ISHV', name, 0.00, 0)
                elif robottype == 'BID_ISHV':
                        return Trader_ISHV('BID_ISHV', name, 0.00, 0)

                elif robottype == 'ZIPPP':
                        return Trader_ZIP('ZIPPP', name, 0.00, 0)
                elif robottype == 'ZIPP':
                        return Trader_ZIP('ZIPP', name, 0.00, 0)
                elif robottype == 'IZIP':
                        return Trader_IZIP_MLOFI('IZIP',name,0.00,0,3)
                elif robottype == 'IGDX':
                        return Trader_IGDX_MLOFI('IGDX', name, 0.00, 0, 3)


                else:
                        sys.exit('FATAL: don\'t know robot type %s\n' % robottype)



        def shuffle_traders(ttype_char, n, traders):
                for swap in range(n):
                        t1 = (n - 1) - swap
                        t2 = random.randint(0, t1)
                        t1name = '%c%02d' % (ttype_char, t1)
                        t2name = '%c%02d' % (ttype_char, t2)
                        traders[t1name].tid = t2name
                        traders[t2name].tid = t1name
                        temp = traders[t1name]
                        traders[t1name] = traders[t2name]
                        traders[t2name] = temp


        n_buyers = 0
        for bs in traders_spec['buyers']:
                ttype = bs[0]
                for b in range(bs[1]):
                        tname = 'B%02d' % n_buyers  # buyer i.d. string
                        traders[tname] = trader_type(ttype, tname)
                        n_buyers = n_buyers + 1

        if n_buyers < 1:
                sys.exit('FATAL: no buyers specified\n')

        if shuffle: shuffle_traders('B', n_buyers, traders)


        n_sellers = 0
        for ss in traders_spec['sellers']:
                ttype = ss[0]
                for s in range(ss[1]):
                        tname = 'S%02d' % n_sellers  # buyer i.d. string
                        traders[tname] = trader_type(ttype, tname)
                        n_sellers = n_sellers + 1

        if n_sellers < 1:
                sys.exit('FATAL: no sellers specified\n')

        if shuffle: shuffle_traders('S', n_sellers, traders)

        if verbose:
                for t in range(n_buyers):
                        bname = 'B%02d' % t
                        print(traders[bname])
                for t in range(n_sellers):
                        bname = 'S%02d' % t
                        print(traders[bname])


        return {'n_buyers':n_buyers, 'n_sellers':n_sellers}



# customer_orders(): allocate orders to traders
# this version only issues LIM orders; LIM that crosses the spread executes as MKT
# parameter "os" is order schedule
# os['timemode'] is either 'periodic', 'drip-fixed', 'drip-jitter', or 'drip-poisson'
# os['interval'] is number of seconds for a full cycle of replenishment
# drip-poisson sequences will be normalised to ensure time of last replenishment <= interval
# parameter "pending" is the list of future orders (if this is empty, generates a new one from os)
# revised "pending" is the returned value
#
# also returns a list of "cancellations": trader-ids for those traders who are now working a new order and hence
# need to kill quotes already on LOB from working previous order
#
#
# if a supply or demand schedule mode is "random" and more than one range is supplied in ranges[],
# then each time a price is generated one of the ranges is chosen equiprobably and
# the price is then generated uniform-randomly from that range
#
# if len(range)==2, interpreted as min and max values on the schedule, specifying linear supply/demand curve
# if len(range)==3, first two vals are min & max, third value should be a function that generates a dynamic price offset
#                   -- the offset value applies equally to the min & max, so gradient of linear sup/dem curve doesn't vary
# if len(range)==4, the third value is function that gives dynamic offset for schedule min,
#                   and fourth is a function giving dynamic offset for schedule max, so gradient of sup/dem linear curve can vary
#
# the interface on this is a bit of a mess... could do with refactoring


def customer_orders(time, last_update, traders, trader_stats, os, pending, base_oid, verbose):


        def sysmin_check(price):
                if price < bse_sys_minprice:
                        print('WARNING: price < bse_sys_min -- clipped')
                        price = bse_sys_minprice
                return price


        def sysmax_check(price):
                if price > bse_sys_maxprice:
                        print('WARNING: price > bse_sys_max -- clipped')

                        price = bse_sys_maxprice
                return price
        

        def getorderprice(i, sched_end, sched, n, mode, issuetime):
                # does the first schedule range include optional dynamic offset function(s)?
                if len(sched[0]) > 2:
                        offsetfn = sched[0][2][0]
                        offsetfn_params = [sched_end] + [p for p in sched[0][2][1] ]
                        if callable(offsetfn):
                                # same offset for min and max
                                offset_min = offsetfn(issuetime, offsetfn_params)
                                offset_max = offset_min
                        else:
                                sys.exit('FAIL: 3rd argument of sched in getorderprice() should be [callable_fn [params]]')
                        if len(sched[0]) > 3:
                                # if second offset function is specfied, that applies only to the max value
                                offsetfn = sched[0][3][0]
                                offsetfn_params = [sched_end] + [p for p in sched[0][3][1] ]
                                if callable(offsetfn):
                                        # this function applies to max
                                        offset_max = offsetfn(issuetime, offsetfn_params)
                                else:
                                        sys.exit('FAIL: 4th argument of sched in getorderprice() should be [callable_fn [params]]')
                else:
                        offset_min = 0.0
                        offset_max = 0.0

                pmin = sysmin_check(offset_min + min(sched[0][0], sched[0][1]))
                pmax = sysmax_check(offset_max + max(sched[0][0], sched[0][1]))
                prange = pmax - pmin
                stepsize = prange / (n - 1)
                halfstep = round(stepsize / 2.0)

                if mode == 'fixed':
                        orderprice = pmin + int(i * stepsize) 
                elif mode == 'jittered':
                        orderprice = pmin + int(i * stepsize) + random.randint(-halfstep, halfstep)
                elif mode == 'random':
                        if len(sched) > 1:
                                # more than one schedule: choose one equiprobably
                                s = random.randint(0, len(sched) - 1)
                                pmin = sysmin_check(min(sched[s][0], sched[s][1]))
                                pmax = sysmax_check(max(sched[s][0], sched[s][1]))
                        orderprice = random.randint(pmin, pmax)
                else:
                        sys.exit('FAIL: Unknown mode in schedule')
                orderprice = sysmin_check(sysmax_check(orderprice))
                return orderprice


        def getissuetimes(n_traders, mode, interval, shuffle, fittointerval):
                # generates a set of issue times for the customer orders to arrive at
                interval = float(interval)
                if n_traders < 1:
                        sys.exit('FAIL: n_traders < 1 in getissuetime()')
                elif n_traders == 1:
                        tstep = interval
                else:
                        tstep = interval / (n_traders - 1)
                arrtime = 0
                issuetimes = []
                for t in range(n_traders):
                        if mode == 'periodic':
                                arrtime = interval
                        elif mode == 'drip-fixed':
                                arrtime = t * tstep
                        elif mode == 'drip-jitter':
                                arrtime = t * tstep + tstep * random.random()
                        elif mode == 'drip-poisson':
                                # poisson requires a bit of extra work
                                interarrivaltime = random.expovariate(n_traders / interval)
                                arrtime += interarrivaltime
                        else:
                                sys.exit('FAIL: unknown time-mode in getissuetimes()')
                        issuetimes.append(arrtime) 
                        
                # at this point, arrtime is the *last* arrival time
                if fittointerval and mode == 'drip-poisson' and (arrtime != interval) :
                        # generated sum of interarrival times longer than the interval
                        # squish them back so that last arrival falls at t=interval
                        for t in range(n_traders):
                                issuetimes[t] = interval * (issuetimes[t] / arrtime)

                # optionally randomly shuffle the times
                if shuffle:
                        for t in range(n_traders):
                                i = (n_traders - 1) - t
                                j = random.randint(0, i)
                                tmp = issuetimes[i]
                                issuetimes[i] = issuetimes[j]
                                issuetimes[j] = tmp
                return issuetimes
        

        def getschedmode(time, os):
                # os is order schedules
                got_one = False
                for sched in os:
                        if (sched['from'] <= time) and (time < sched['to']) :
                                # within the timezone for this schedule
                                schedrange = sched['ranges']
                                mode = sched['stepmode']
                                sched_end_time = sched['to']
                                got_one = True
                                exit  # jump out the loop -- so the first matching timezone has priority over any others
                if not got_one:
                        sys.exit('Fail: time=%5.2f not within any timezone in os=%s' % (time, os))
                return (schedrange, mode, sched_end_time)
        

        n_buyers = trader_stats['n_buyers']
        n_sellers = trader_stats['n_sellers']

        shuffle_times = True

        cancellations = []

        oid = base_oid

        max_qty = 1

        if len(pending) < 1:
                # list of pending (to-be-issued) customer orders is empty, so generate a new one
                new_pending = []

                # demand side (buyers)
                issuetimes = getissuetimes(n_buyers, os['timemode'], os['interval'], shuffle_times, True)
                ordertype = 'Bid'
                orderstyle = 'LIM'
                (sched, mode, sched_end) = getschedmode(time, os['dem'])
                for t in range(n_buyers):
                        issuetime = time + issuetimes[t]
                        tname = 'B%02d' % t
                        ## flag
                        orderprice = getorderprice(t, sched_end, sched, n_buyers, mode, issuetime)
                        # if time<101 or (time>201 and time <301) or (time>401 and time<501):
                        #         orderprice = 150
                        # else:
                        #         orderprice = 100
                        orderqty = random.randint(1,max_qty)
                        # order = Order(tname, ordertype, orderstyle, orderprice, orderqty, issuetime, None, oid)
                        order = Assignment("CUS", tname, ordertype, orderstyle, orderprice, orderqty, issuetime, None, oid)
                        oid += 1
                        new_pending.append(order)
                        
                # supply side (sellers)
                issuetimes = getissuetimes(n_sellers, os['timemode'], os['interval'], shuffle_times, True)
                ordertype = 'Ask'
                orderstyle = 'LIM'
                (sched, mode, sched_end) = getschedmode(time, os['sup'])
                for t in range(n_sellers):
                        issuetime = time + issuetimes[t]
                        tname = 'S%02d' % t
                        orderprice = getorderprice(t, sched_end, sched, n_sellers, mode, issuetime)
                        # if time<101 or (time>201 and time <301) or (time>401 and time<501):
                        #         orderprice = 50
                        # else:
                        #         orderprice = 20
                        orderqty = random.randint(1, max_qty)
                        # order = Order(tname, ordertype, orderstyle, orderprice, orderqty, issuetime, None, oid)
                        order = Assignment("CUS", tname, ordertype, orderstyle, orderprice, orderqty, issuetime, None, oid)
                        oid += 1
                        new_pending.append(order)
        else:
                # there are pending future orders: issue any whose timestamp is in the past
                new_pending = []
                for order in pending:
                        if order.time < time:
                                # this order should have been issued by now
                                # issue it to the trader
                                tname = order.trad_id
                                response = traders[tname].add_cust_order(order, verbose)
                                if verbose: print('Customer order: %s %s' % (response, order))
                                if response == 'LOB_Cancel' :
                                    cancellations.append(tname)
                                    if verbose: print('Cancellations: %s' % (cancellations))
                                # and then don't add it to new_pending (i.e., delete it)
                        else:
                                # this order stays on the pending list
                                new_pending.append(order)
        return [new_pending, cancellations, oid]



# one session in the market
def market_session(sess_id, starttime, endtime, trader_spec, order_schedule, summaryfile, tapedumpfile, blotterdumpfile,
                   dump_each_trade, verbose):

        n_exchanges = 1

        tape_depth = 5 # number of most-recent items from tail of tape to be published at any one time

        verbosity = False

        verbose = verbosity             # main loop verbosity
        orders_verbose = verbosity
        lob_verbose = False
        process_verbose = False
        respond_verbose = False
        bookkeep_verbose = False

        # fname = 'prices' + sess_id +'.csv'
        # prices_data_file = open(fname, 'w')

        # initialise the exchanges
        exchanges = []
        for e in range(n_exchanges):
                eid = "Exch%d" % e
                exch = Exchange(eid)
                exchanges.append(exch)
                if verbose: print('Exchange[%d] =%s' % (e, str(exchanges[e])))

        # create a bunch of traders
        traders = {}
        trader_stats = populate_market(trader_spec, traders, True, verbose)


        # print 'describe traders:'
        # for tid in traders:
        #         print 'trader.ttype: %s , trader.tid: %s' %(traders[tid].ttype,tid)


        # timestep set so that can process all traders in one second
        # NB minimum inter-arrival time of customer orders may be much less than this!!
        timestep = 1.0 / float(trader_stats['n_buyers'] + trader_stats['n_sellers'])
        
        duration = float(endtime - starttime)

        last_update = -1.0

        time = starttime

        next_order_id = 0

        pending_cust_orders = []

        if verbose: print('\n%s;  ' % (sess_id))

        tid = None

        while time < endtime:

                # how much time left, as a percentage?
                time_left = (endtime - time) / duration
                if verbose: print('\n\n%s; t=%08.2f (percent remaining: %4.1f/100) ' % (sess_id, time, time_left*100))

                trade = None

                # get any new assignments (customer orders) for traders to execute
                # and also any customer orders that require previous orders to be killed
                [pending_cust_orders, kills, noid] = customer_orders(time, last_update, traders, trader_stats,
                                                                     order_schedule, pending_cust_orders, next_order_id, orders_verbose)

                next_order_id = noid

                if verbose:
                        print('t:%f, noid=%d, pending_cust_orders:' % (time, noid))
                        for order in pending_cust_orders: print('%s; ' % str(order))

                # if any newly-issued customer orders mean quotes on the LOB need to be cancelled, kill them
                if len(kills) > 0:
                        if verbose: print('Kills: %s' % (kills))
                        for kill in kills:
                                # if verbose: print('lastquote=%s' % traders[kill].lastquote)
                                if traders[kill].lastquote != None :
                                        if verbose: print('Killing order %s' % (str(traders[kill].lastquote)))

                                        can_order = traders[kill].lastquote
                                        can_order.ostyle = "CAN"
                                        exch_response = exchanges[0].process_order(time, can_order, process_verbose)
                                        exch_msg = exch_response['trader_msgs']
                                        # do the necessary book-keeping
                                        # NB this assumes CAN results in a single message back from the exchange
                                        traders[kill].bookkeep(exch_msg[0], time, bookkeep_verbose)

                for t in traders:
                        if len(traders[t].orders) > 0:
                                # print("Tyme=%5.2d TID=%s Orders[0]=%s" % (time, traders[t].tid, traders[t].orders[0]))
                                dummy = 0 # NOP

                # get public lob data from each exchange
                lobs = []
                for e in range(n_exchanges):
                        exch = exchanges[e]
                        lob = exch.publish_lob(time, tape_depth, lob_verbose)
                        # if verbose: print ('Exchange %d, Published LOB=%s' % (e, str(lob)))

                        lobs.append(lob)


                # quantity-spike injection
                # this next bit is a KLUDGE that is VERY FRAGILE and has lots of ARBITRARY CONSTANTS in it :-(
                # it is introduced for George Church's project
                # to edit this you have to know how many traders there are (specified in main loop)
                # and you have to know the details of the supply and demand curves too (again, spec in main loop)
                # before public release of this code, tidy it up and parameterise it nicely
                # triggertime = 20
                # replenish_period = 20
                # highest_buyer_index = 10         # this buyer has the highest limit price
                # highest_seller_index = 20
                # big_qty = 222
                #
                # if time > (triggertime - 3*timestep)  and ((time+3*timestep) % replenish_period) <= (timestep):
                #         # sys.exit('Bailing at injection trigger, time = %f' % time)
                #         print ('time: %f')%(time)
                #         # here we inject big quantities nto both buyer and seller sides... hopefully the injected traders will do a deal
                #         pending_cust_orders[0].qty = big_qty
                #
                #
                #         # pending_cust_orders[highest_seller_index-1].qty = big_qty
                #
                #         if verbose: print ('t:%f SPIKE INJECTION (Post) Exchange %d, Published LOB=%s' % (time, e, str(lob)))
                #
                #         print('t:%f, Spike Injection: , microp=%s, pending_cust_orders:' % (time, lob['microprice']) )
                #         for order in pending_cust_orders: print('%s; ' % str(order))

                triggertime = 100
                replenish_period = 100
                highest_buyer_index = 10         # this buyer has the highest limit price
                highest_seller_index = 20
                big_qty = 200
                if time > (triggertime - 3*timestep) and ((time+3*timestep) % replenish_period) <= (2 * timestep):
                        # sys.exit('Bailing at injection trigger, time = %f' % time)
                        ##print "inject at", time
                        for assigment in pending_cust_orders:
                                if traders[assigment.trad_id].ttype == 'AAAA':
                                        assigment.qty = big_qty
                                        # print 'block order comes in'
                                        # print 'trad_id: %s, price: %i qty: %i , time : %i' %(assigment.trad_id,assigment.price,assigment.qty,assigment.time)

                # get a quote (or None) from a randomly chosen trader

                # first randomly select a trader id
                old_tid = tid
                while tid == old_tid:
                        tid = list(traders.keys())[random.randint(0, len(traders) - 1)]

                # currently, all quotes/orders are issued only to the single exchange at exchanges[0]
                # it is that exchange's responsibility to then deal with Order Protection / trade-through (Reg NMS Rule611)
                # i.e. the exchange logic could/should be extended to check the best LOB price of each other exchange
                # that is yet to be implemented here
                # if((time >= replenish_period and time % replenish_period <= 0.001)):
                #         print 'time: %f' %(time)
                #         tid = 'B00'
                #         order = traders[tid].getorder(time, time_left, lobs[0], verbose)
                #         print str(order);
                #         print '11111111111111111111111'
                #
                # else:
                #         order = traders[tid].getorder(time, time_left, lobs[0], verbose)

                # if((time >= replenish_period and time % replenish_period <= 0.05)):
                #         print 'time: %f' %(time)
                #         tid = 'B00'
                #         order = traders[tid].getorder(time, time_left, lobs[0], verbose)
                #         print str(order);
                #         print '11111111111111111111111'
                #
                # else:
                #         order = traders[tid].getorder(time, time_left, lobs[0], verbose)

                order = traders[tid].getorder(time, time_left, lobs[0], verbose)



                if order != None:
                    # print ''
                    # print ''
                    # print ''
                    # print('Trader Order: %s' % str(order))

                    order.myref = traders[tid].orders[0].assignmentid  # attach customer order ID to this exchange order
                    if verbose: print('Order with myref=%s' % order.myref)

                    # Sanity check: catch bad traders here
                    traderprice = traders[tid].orders[0].price
                    if order.otype == 'Ask' and order.price < traderprice: sys.exit('Bad ask: Trader.price %s, Quote: %s' % (traderprice,order))
                    if order.otype == 'Bid' and order.price > traderprice: sys.exit('Bad bid: Trader.price %s, Quote: %s' % (traderprice,order))


                    # how many quotes does this trader already have sat on an exchange?

                    if len(traders[tid].quotes) >= traders[tid].max_quotes :
                            # need to clear a space on the trader's list of quotes, by deleting one
                            # new quote replaces trader's oldest previous quote
                            # bit of a  kludge -- just deletes oldest quote, which is at head of list
                            # THIS SHOULD BE IN TRADER NOT IN MAIN LOOP?? TODO
                            can_order = traders[tid].quotes[0]
                            if verbose: print('> can_order %s' % str(can_order))
                            can_order.ostyle = "CAN"
                            if verbose: print('> can_order %s' % str(can_order))

                            # send cancellation to exchange
                            exch_response = exchanges[0].process_order(time, can_order, process_verbose)
                            exch_msg = exch_response['trader_msgs']
                            tape_sum = exch_response['tape_summary']

                            if verbose:
                                    print('>Exchanges[0]ProcessOrder: tradernquotes=%d, quotes=[' % len(traders[tid].quotes))
                                    for q in traders[tid].quotes: print('%s' % str(q))
                                    print(']')
                                    for t in traders:
                                            if len(traders[t].orders) > 0:
                                                    # print(">Exchanges[0]ProcessOrder: Tyme=%5.2d TID=%s Orders[0]=%s" % (time, traders[t].tid, traders[t].orders[0]))
                                                    NOP = 0
                                            if len(traders[t].quotes) > 0:
                                                    # print(">Exchanges[0]ProcessOrder: Tyme=%5.2d TID=%s Quotes[0]=%s" % (time, traders[t].tid, traders[t].quotes[0]))
                                                    NOP = 0

                            # do the necessary book-keeping
                            # NB this assumes CAN results in a single message back from the exchange
                            traders[tid].bookkeep(exch_msg[0], time, bookkeep_verbose)

                    if verbose:
                            # print('post-check: tradernquotes=%d, quotes=[' % len(traders[tid].quotes))
                            for q in traders[tid].quotes: print('%s' % str(q))
                            print(']')
                            for t in traders:
                                if len(traders[t].orders) > 0:
                                        # print("PostCheck Tyme=%5.2d TID=%s Orders[0]=%s" % (time, traders[t].tid, traders[t].orders[0]))
                                        if len(traders[t].quotes) > 0:
                                                # print("PostCheck Tyme=%5.2d TID=%s Quotes[0]=%s" % (time, traders[t].tid, traders[t].quotes[0]))
                                                NOP = 0

                                if len(traders[t].orders) > 0 and traders[t].orders[0].astyle == "CAN":
                                        sys.stdout.flush()
                                        sys.exit("CAN error")


                    # add order to list of live orders issued by this trader
                    traders[tid].quotes.append(order)

                    if verbose: print('Trader %s quotes[-1]: %s' % (tid, traders[tid].quotes[-1]))

                    # send this order to exchange and receive response
                    exch_response = exchanges[0].process_order(time, order, process_verbose)
                    exch_msgs = exch_response['trader_msgs']
                    tape_sum = exch_response['tape_summary']

                    # because the order just processed might have changed things, now go through each
                    # order resting at the exchange and see if it can now be processed
                    # applies to AON, ICE, OSO, and OCO





                    #print('Exch_Msgs: ')
                    # if exch_msgs == None: pass
                    # else:
                    #         for msg in exch_msgs:
                    #             print('Msg=%s' % msg)

                    if exch_msgs != None and len(exch_msgs) > 0:
                                # messages to process
                                for msg in exch_msgs:
                                        if verbose: print('Message: %s' % msg)
                                        traders[msg.tid].bookkeep(msg, time, bookkeep_verbose)


                    # traders respond to whatever happened
                    # needs to be updated for multiple exchanges
                    lob = exchanges[0].publish_lob(time, tape_depth, lob_verbose)

                    s = '%6.2f, ' % time
                    for t in traders:
                                # NB respond just updates trader's internal variables
                                # doesn't alter the LOB, so processing each trader in
                                # sequence (rather than random/shuffle) isn't a problem
                                traders[t].respond(time, lob, tape_sum, respond_verbose)

                                # if traders[t].ttype == 'ISHV':
                                #         print('%6.2f, ISHV Print, %s' % (time, str(traders[t])))
                                #         lq = traders[t].lastquote
                                #         print('lq = %s' % lq)
                                #         if lq != None :
                                #                 price = lq.price
                                #         else: price = None
                                #         if price == None: s = s + '-1, '
                                #         else: s = s + '%s, ' % price
                    # prices_data_file.write('%s\n' % s)

                    # if (lob['microprice'] == None or lob['midprice'] == None):
                    #         print 'microprice is none'
                    #         print 'midprice is none '
                    # print 'microprice: '
                    # print lob['microprice']
                    # print 'midprice: '
                    # print lob['midprice']
                    # print 'bid anon:'
                    # print lob['bids']['lob']
                    # print 'ask anon:'
                    # print lob['asks']['lob']

                time = time + timestep


        # end of an experiment -- dump the tape
        exchanges[0].dump_tape(sess_id, tapedumpfile, 'keep',traders)


        # traders dump their blotters
        for t in traders:
                tid = traders[t].tid
                ttype = traders[t].ttype
                balance = traders[t].balance
                blot = traders[t].blotter
                blot_len = len(blot)
                # build csv string for all events in blotter
                csv = ''
                estr = "TODO "
                for e in blot:
                        # print(blot)
                        # estr = '%s, %s, %s, %s, %s, %s, ' % (e['type'], e['time'], e['price'], e['qty'], e['party1'], e['party2'])
                        csv = csv + estr
                blotterdumpfile.write('%s, %s, %s, %s, %s, %s\n' % (sess_id, tid, ttype, balance, blot_len, csv))

        # write summary trade_stats for this experiment (end-of-session summary ONLY)
        for e in range(n_exchanges):
                trade_stats(sess_id, traders, summaryfile, time, exchanges[e].publish_lob(time, None, lob_verbose))



#############################

# # Below here is where we set up and run a series of experiments


if __name__ == "__main__":


    start_time = 0.0
    end_time = 200.0
    duration = end_time - start_time

    range1 = (50,50)
    range2 = (20,20)
    supply_schedule = [{'from': 0, 'to': end_time, 'ranges': [range1], 'stepmode': 'fixed'}]
    # supply_schedule = [{'from': 0, 'to': 100, 'ranges': [(50,50)], 'stepmode': 'fixed'},
    #                    {'from': 100, 'to': 200, 'ranges': [(50,150)], 'stepmode': 'fixed'},
    #                    {'from': 200, 'to': 300, 'ranges': [(50,150)], 'stepmode': 'fixed'},
    #                    {'from': 300, 'to': 500, 'ranges': [(50,50)], 'stepmode': 'fixed'}
    #
    #                    ]

    range3 = (150, 150)
    range4 = (100, 100)
    demand_schedule = [{'from': 0, 'to': end_time, 'ranges': [range3], 'stepmode': 'fixed'}]
    # demand_schedule = [{'from': 0, 'to': 100, 'ranges': [(150,150)], 'stepmode': 'fixed'},
    #                    {'from': 100, 'to': 200, 'ranges': [(50,150)], 'stepmode': 'fixed'},
    #                    {'from': 200, 'to': 300, 'ranges': [(150,150)], 'stepmode': 'fixed'},
    #                    {'from': 300, 'to': 500, 'ranges': [(50,150)], 'stepmode': 'fixed'}
    #
    #                    ]

    order_sched = {'sup': supply_schedule, 'dem': demand_schedule,
                   'interval': 100,
                   'timemode': 'periodic'}

    ## 'AAAA' holds the block order
    buyers_spec = [('AAA',10),('AAAA',10)]
    sellers_spec = [ ('AA',10),('IAA_MLOFI',10)]
    # buyers_spec = [('BID_IGDX_3', 10), ('BID_IZIP_3', 10), ('BID_IAA_3', 10),('BID_ISHV_3', 10),  ('AAAA', 10)]
    # sellers_spec = [('BID_IGDX_3', 10), ('BID_IZIP_3', 10), ('BID_IAA_3', 10),('BID_ISHV_3', 10),  ('AAAA', 10)]
    traders_spec = {'sellers':sellers_spec, 'buyers':buyers_spec}

    sys.stdout.flush()

    fname = 'Mybalances.csv'
    summary_data_file = open(fname, 'w')

    fname = 'Mytapes.csv'
    tape_data_file = open(fname, 'w')

    fname = 'Myblotters.csv'
    blotter_data_file = open(fname, 'w')

    for session in range(100):
            sess_id = 'Test%02d' % session
            print('Session %s; ' % sess_id)


            market_session(sess_id, start_time, end_time, traders_spec, order_sched, summary_data_file, tape_data_file, blotter_data_file, True, False)

    summary_data_file.close()
    tape_data_file.close()
    blotter_data_file.close()

    print('\n Experiment Finished')
