# Trader subclass ZIP
# After Cliff 1997


from BSE2_msg_classes import Assignment, Order, Exch_msg
from BSE_trader_agents import Trader;
import random
import math

bse_sys_minprice = 1  # minimum price in the system, in cents/pennies
bse_sys_maxprice = 200  # maximum price in the system, in cents/pennies

class Trader_GDX(Trader):

        def __init__(self, ttype, tid, balance, time):
                Trader.__init__(self, ttype, tid, balance, time)
                self.prev_orders = []
                self.active = False
                self.limit = None
                self.job = None



                #memory of all bids and asks and accepted bids and asks
                self.outstanding_bids = []
                self.outstanding_asks = []
                self.accepted_asks = []
                self.accepted_bids = []

                self.price = -1

                # memory of best price & quantity of best bid and ask, on LOB on previous update
                self.prev_best_bid_p = None
                self.prev_best_bid_q = None
                self.prev_best_ask_p = None
                self.prev_best_ask_q = None

                self.first_turn = True

                self.gamma = 0.1

                self.holdings = 10
                self.remaining_offer_ops = 10
                self.values = [[0 for n in range(self.remaining_offer_ops)] for m in range(self.holdings)]


        def getorder(self, time, countdown, lob, verbose):
                if len(self.orders) < 1:
                        self.active = False
                        order = None
                else:
                        self.active = True
                        self.limit = self.orders[0].price
                        self.job = self.orders[0].atype

                        #calculate price
                        if self.job == 'Bid':
                                self.price = self.calc_p_bid(self.holdings - 1, self.remaining_offer_ops - 1)
                        if self.job == 'Ask':
                                self.price = self.calc_p_ask(self.holdings - 1, self.remaining_offer_ops - 1)

                        order = Order(self.tid, self.job, 'LIM',self.price, self.orders[0].qty, time, None,  -1)
                        self.lastquote = order

                if self.first_turn or self.price == -1:
                        if self.job == 'Bid':
                                order = Order(self.tid, self.job, 'LIM',bse_sys_minprice+1 , self.orders[0].qty, time, None, -1)
                        if self.job == 'Ask':
                                order = Order(self.tid, self.job, 'LIM',bse_sys_maxprice-1 , self.orders[0].qty, time, None, -1)


                return order

        def calc_p_bid(self, m, n):
                best_return = 0
                best_bid = 0
                second_best_return = 0
                second_best_bid = 0

                #first step size of 1 get best and 2nd best
                for i in [x*2 for x in range(int(self.limit/2))]:
                        thing = self.belief_buy(i) * ((self.limit - i) + self.gamma*self.values[m-1][n-1]) + (1-self.belief_buy(i) * self.gamma * self.values[m][n-1])
                        if thing > best_return:
                                second_best_bid = best_bid
                                second_best_return = best_return
                                best_return = thing
                                best_bid = i

                #always best bid largest one
                if second_best_bid > best_bid:
                        a = second_best_bid
                        second_best_bid = best_bid
                        best_bid = a

                #then step size 0.05
                for i in [x*0.05 for x in range(int(second_best_bid), int(best_bid))]:
                        thing = self.belief_buy(i + second_best_bid) * ((self.limit - (i + second_best_bid)) + self.gamma*self.values[m-1][n-1]) + (1-self.belief_buy(i + second_best_bid) * self.gamma * self.values[m][n-1])
                        if thing > best_return:
                                best_return = thing
                                best_bid = i + second_best_bid

                return best_bid

        def calc_p_ask(self, m, n):
                best_return = 0
                best_ask = self.limit
                second_best_return = 0
                second_best_ask = self.limit

                #first step size of 1 get best and 2nd best
                for i in [x*2 for x in range(int(self.limit/2))]:
                        j = i + self.limit
                        thing =  self.belief_sell(j) * ((j - self.limit) + self.gamma*self.values[m-1][n-1]) + (1-self.belief_sell(j) * self.gamma * self.values[m][n-1])
                        if thing > best_return:
                                second_best_ask = best_ask
                                second_best_return = best_return
                                best_return = thing
                                best_ask = j
                #always best ask largest one
                if second_best_ask > best_ask:
                        a = second_best_ask
                        second_best_ask = best_ask
                        best_ask = a

                #then step size 0.05
                for i in [x*0.05 for x in range(int(second_best_ask), int(best_ask))]:
                        thing = self.belief_sell(i + second_best_ask) * (((i + second_best_ask) - self.limit) + self.gamma*self.values[m-1][n-1]) + (1-self.belief_sell(i + second_best_ask) * self.gamma * self.values[m][n-1])
                        if thing > best_return:
                                best_return = thing
                                best_ask = i + second_best_ask

                return best_ask

        def belief_sell(self, price):
                accepted_asks_greater = 0
                bids_greater = 0
                unaccepted_asks_lower = 0
                for p in self.accepted_asks:
                        if p >= price:
                                accepted_asks_greater += 1
                for p in [thing[0] for thing in self.outstanding_bids]:
                        if p >= price:
                                bids_greater += 1
                for p in [thing[0] for thing in self.outstanding_asks]:
                        if p <= price:
                                unaccepted_asks_lower += 1

                if accepted_asks_greater + bids_greater + unaccepted_asks_lower == 0:
                        return 0
                return (accepted_asks_greater + bids_greater) / (accepted_asks_greater + bids_greater + unaccepted_asks_lower)

        def belief_buy(self, price):
                accepted_bids_lower = 0
                asks_lower = 0
                unaccepted_bids_greater = 0
                for p in self.accepted_bids:
                        if p <= price:
                                accepted_bids_lower += 1
                for p in [thing[0] for thing in self.outstanding_asks]:
                        if p <= price:
                                asks_lower += 1
                for p in [thing[0] for thing in self.outstanding_bids]:
                        if p >= price:
                                unaccepted_bids_greater += 1
                if accepted_bids_lower + asks_lower + unaccepted_bids_greater == 0:
                        return 0
                return (accepted_bids_lower + asks_lower) / (accepted_bids_lower + asks_lower + unaccepted_bids_greater)

        def respond(self, time, lob, trade, verbose):
                # what, if anything, has happened on the bid LOB?
                self.outstanding_bids = lob['bids']['lob']
                bid_improved = False
                bid_hit = False
                lob_best_bid_p = lob['bids']['bestp']
                lob_best_bid_q = None
                if lob_best_bid_p != None:
                        # non-empty bid LOB
                        lob_best_bid_q = lob['bids']['lob'][-1][1]
                        if self.prev_best_bid_p < lob_best_bid_p :
                                # best bid has improved
                                # NB doesn't check if the improvement was by self
                                bid_improved = True
                        elif trade != None and ((self.prev_best_bid_p > lob_best_bid_p) or ((self.prev_best_bid_p == lob_best_bid_p) and (self.prev_best_bid_q > lob_best_bid_q))):
                                # previous best bid was hit
                                self.accepted_bids.append(self.prev_best_bid_p)
                                bid_hit = True
                elif self.prev_best_bid_p != None:
                        # the bid LOB has been emptied: was it cancelled or hit?
                        last_tape_item = lob['tape'][-1]
                        if last_tape_item['type'] == 'Cancel' :
                                bid_hit = False
                        else:
                                bid_hit = True

                # what, if anything, has happened on the ask LOB?
                self.outstanding_asks = lob['asks']['lob']
                ask_improved = False
                ask_lifted = False
                lob_best_ask_p = lob['asks']['bestp']
                lob_best_ask_q = None
                if lob_best_ask_p != None:
                        # non-empty ask LOB
                        lob_best_ask_q = lob['asks']['lob'][0][1]
                        if self.prev_best_ask_p > lob_best_ask_p :
                                # best ask has improved -- NB doesn't check if the improvement was by self
                                ask_improved = True
                        elif trade != None and ((self.prev_best_ask_p < lob_best_ask_p) or ((self.prev_best_ask_p == lob_best_ask_p) and (self.prev_best_ask_q > lob_best_ask_q))):
                                # trade happened and best ask price has got worse, or stayed same but quantity reduced -- assume previous best ask was lifted
                                self.accepted_asks.append(self.prev_best_ask_p)
                                ask_lifted = True
                elif self.prev_best_ask_p != None:
                        # the ask LOB is empty now but was not previously: canceled or lifted?
                        last_tape_item = lob['tape'][-1]
                        if last_tape_item['type'] == 'Cancel' :
                                ask_lifted = False
                        else:
                                ask_lifted = True


                #populate expected values
                if self.first_turn:
                        # print "populating"
                        self.first_turn = False
                        for n in range(1, self.remaining_offer_ops):
                                for m in range(1, self.holdings):
                                            if self.job == 'Bid':
                                                    #BUYER
                                                    self.values[m][n] = self.calc_p_bid(m, n)

                                            if self.job == 'Ask':
                                                    #BUYER
                                                    self.values[m][n] = self.calc_p_ask(m, n)
                        # print "done"


                deal = bid_hit or ask_lifted


                # remember the best LOB data ready for next response
                self.prev_best_bid_p = lob_best_bid_p
                self.prev_best_bid_q = lob_best_bid_q
                self.prev_best_ask_p = lob_best_ask_p
                self.prev_best_ask_q = lob_best_ask_q

