# Assignment:
# The details of a customer's order/request, assigned to a trader
class Assignment:

        def __init__(self, customer_id, trader_id, otype, ostyle, price, qty, time, endtime, assignmentid):
                self.cust_id = customer_id      # customer identifier
                self.trad_id = trader_id        # trader this customer order is assigned to
                self.atype = otype              # order type (buy or sell)
                self.astyle = ostyle            # order style: MKT, LIM, etc
                self.price = price              # price
                self.qty = qty                  # quantity
                self.time = time                # timestamp: time at which customer issued order
                self.endtime = endtime          # time at which order should expire (e.g. for GFD and AON orders)
                self.assignmentid = assignmentid  # i.d. (unique identifier for each assignment)


        def __str__(self):
                return '[%s %s %s %s P=%03d Q=%s T=%5.2f AID:%d]' % \
                       (self.cust_id, self.trad_id, self.atype, self.astyle, self.price, self.qty, self.time, self.assignmentid)


# Order/quote, submitted by trader to exchange
# has a trader id, a type (buy/sell), a style (LIM, MKT, etc), a price,
# a quantity, a timestamp, and a unique i.d.
# The order-style may require additional parameters which are bundled into style_params (=None if not)
class Order:

        def __init__(self, trader_id, otype, ostyle, price, qty, time, endtime, orderid):
                self.tid = trader_id    # trader i.d.
                self.otype = otype      # order type (bid or ask -- what side of LOB is it for)
                self.ostyle = ostyle    # order style: MKT, LIM, etc
                self.price = price      # price
                self.qty = qty          # quantity
                self.time = time        # timestamp
                self.endtime = endtime  # time at which exchange deletes order (e.g. for GFD and AON orders)
                self.orderid = orderid  # quote i.d. (unique to each quote, assigned by exchange)
                self.myref = None       # trader's own reference for this order -- used to link back to assignment-ID
                self.styleparams = None # style parameters -- initially null, filled in later

        def __str__(self):
                return '[%s %s %s P=%03d Q=%s T=%5.2f OID:%d Params=%s MyRef=%s]' % \
                       (self.tid, self.otype, self.ostyle, self.price, self.qty, self.time, self.orderid, str(self.styleparams), self.myref)


# structure of the messages that the exchange sends back to the traders after processing an order
class Exch_msg:

        def __init__(self, trader_id, order_id, eventtype, transactions, revised_order, fee, balance):
                self.tid = trader_id            # trader i.d.
                self.oid = order_id             # order i.d.
                self.event = eventtype          # what happened? (ACKnowledged|PARTial|FILLed|FAILure)
                self.trns = transactions        # list of transactions (price, qty, etc) details for this order
                self.revo = revised_order       # revised order as created by exchange matching engine
                self.fee = fee                  # exchange fee
                self.balance = balance          # exchange's record of this trader's balance

        def __str__(self):
                return 'TID:%s OID:%s Event:%s Trns:%s RevO:%s Fee:%d Bal:%d' % \
                       (self.tid, self.oid, self.event, str(self.trns), str(self.revo), self.fee, self.balance)
